# -*- coding: utf-8 -*-
"""本体知识层 LLM 决策回路测试：
- 合法动作被 LLM 选用并通过 validate_action (via_llm=True)
- 非法动作被 validate_action 拒绝，N 次重问后回退规则 (via_llm=False)
- 影子对齐：LLM 与规则不一致时只记录对齐、执行规则、不改动作
"""
import os
import tempfile

os.environ["ONT_DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["ONT_USE_LLM"] = "1"
import app.ontology as ont
ont.init()
import pytest

from app.ontology import ontology, llm as llm_mod, execution, store, orbit

ADDR_SUP = "s2@x.com"


def _task():
    return {
        "task_id": "OT-X", "from_email": "eng@x.com", "status": "INIT",
        "internal_status": "R_INIT", "external_status": "R_SEND",
        "threat_msg_id": "<A@x>", "mode": "ontology",
        "spare_info": {
            "project_no": "P1", "project_name": "N", "part_type": "内存条", "brand": "K",
            "pn": "PN1", "spec": "s", "condition": "全新", "count": "2",
            "address": "a", "urgent": "5min",
            "suppliers": [{"name": "供", "email": ADDR_SUP}],
            "approver_emails": ["ap@x.com"], "quotes": [], "b_msg_ids": [],
            "d_msg_id": "", "e_msg_id": "",
        },
    }


def _ctx():
    return orbit.ctx_from_task(_task())


def test_llm_uses_valid_action():
    calls = {"n": 0}

    def fake_ask(allowed, sysp, user, rej):
        calls["n"] += 1
        return {"action": "distributeInquiry", "reason": "供应商就绪、尚未询价"}
    llm_mod._ask_llm_action = fake_ask
    aid, reason, via = llm_mod.llm_decide_action(_ctx(), task=_task())
    assert via is True and aid == "distributeInquiry", (aid, via, reason)


def test_llm_rejects_invalid_then_fallback():
    # 非法动作 confirmOrderToSupplier（无报价/未审批）→ 校验拒绝 → 3次重问 → 回退规则(distributeInquiry)
    llm_mod._ask_llm_action = lambda a, s, u, r: {"action": "confirmOrderToSupplier", "reason": "下单"}
    aid, reason, via = llm_mod.llm_decide_action(_ctx(), task=_task())
    assert via is False, "非法动作最终应回退规则"
    assert aid == "distributeInquiry", f"应回退到规则动作, 得到 {aid}"


def test_shadow_logs_alignment_and_executes_rule(monkeypatch):
    os.environ["ONT_SHADOW"] = "1"
    monkeypatch.setattr(execution, "_GOV", {"mode": "ontology", "roll": 1.0, "exec": True, "llm": False})

    class FakeMG:
        def __init__(self):
            self.sent = []
        def send_mail(self, **kw):
            self.sent.append({"to": kw.get("to"), "subject": kw.get("subject")})
            return {"message_id": "<M@x>"}
        def mark_seen_by_message_id(self, m): return True
        def read_inbox(self, **kw): return {"mails": []}

    # 让 LLM 提议一个与规则不一致的动作（规则=distributeInquiry，LLM=receiveSupplierQuote）
    llm_mod._ask_llm_action = lambda a, s, u, r: {"action": "receiveSupplierQuote", "reason": "错拍"}
    store.upsert_task(_task())
    mg = FakeMG()
    try:
        reports = orbit.drive("ontology", use_llm=False, mg=mg)
    finally:
        del os.environ["ONT_SHADOW"]
        monkeypatch.setattr(execution, "_GOV", {"mode": "ontology", "roll": 1.0, "exec": True, "llm": False})
    # 影子下执行的是规则动作（distributeInquiry，向供应商发询价B）
    r = reports[0]
    assert r["action"] == "distributeInquiry", r
    assert r["via_llm"] is False, "影子模式应执行规则、不执行 LLM 动作"
    assert any(x.get("b_msg_ids") for x in [store.get_task("OT-X")["spare_info"]]), "应执行规则的 distributeInquiry(发B)"

    # 对齐记录应已落审计（记录 LLM 提议→校验→落位）
    recs = store.list_audit(biz_id="OT-X", limit=50)
    assert any(r_.get("action", "").startswith("align:") for r_ in recs), "应记录影子对齐"