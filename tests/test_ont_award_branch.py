# -*- coding: utf-8 -*-
"""定标模式分支：A 邮件声明「无特殊要求，最低价中标」→ 自动轨，否则人工轨。

自动轨（auto_award=True）：报价收集完 → AI 比价 → 发 D 审批汇总 → 审批通过 → 发 E 订货
人工轨（auto_award=False）：报价收集完 → 发 P 定标请求给项目经理 → PM 线下比选/送审批
                          → 审批人在 P 线程内回复「确认采购」→ 发 E 订货

关键回归点：
  1. 短语识别对空格/全半角标点容错；
  2. 人工轨发 P 时**必须抄送审批人**，否则审批回复脱离线程、任务永远收不回审批结论；
  3. 未配置项目经理时人工轨要留下 blocked 审计，而不是静默跳过；
  4. 人工轨的审批回复必须能被 _thread_match 认领（p_msg_id 已纳入已知线程集合）。
"""
import os
import tempfile

os.environ.setdefault("ONT_DB_PATH", tempfile.mktemp(suffix=".db"))
os.environ["ONT_REQUESTERS"] = "eng@corp.com"
os.environ["ONT_MAIL_USERNAME"] = "b4@corp.com"

import pytest

import app.ontology as ont
ont.init()
from app.ontology import orbit, execution, store
from app.ontology.ingest import _auto_award, parse_inquiry_fields


ENG = "eng@corp.com"
B4 = "b4@corp.com"
S1 = "s1@x.com"   # 供应商A（最低价 1000）
S2 = "s2@x.com"   # 供应商B（1200）
AP = "ap@x.com"   # 审批人
PM = "pm@corp.com"  # 项目经理
SUPPLIERS = [{"name": "供A", "email": S1}, {"name": "供B", "email": S2}]
APPROVERS = [AP]
PMS = [PM]

# 声明自动定标的完整询价正文
BODY_AUTO = ("项目编号: PRJ001\n项目名称: 服务器硬盘备件\n备件类型: 硬盘\n"
             "品牌: Seagate\n型号: ST8000\n规格: 8TB SATA\n成色: 全新\n"
             "数量: 2\n收货地址: 北京市海淀区科技路1号\n紧急程度: 3天\n"
             "无特殊要求，最低价中标\n询价")
# 未声明 → 人工轨
BODY_MANUAL = BODY_AUTO.replace("无特殊要求，最低价中标\n", "")

QUOTES = [
    {"email": S1, "unit_price": "1000", "msg_id": "<Q1@t>", "refs": "<A@t>"},
    {"email": S2, "unit_price": "1200", "msg_id": "<Q2@t>", "refs": "<A@t>"},
]


class FakeMG:
    def __init__(self):
        self.mailbox = []
        self.sent = []
        self.seen = []
        self._n = 0

    def read_inbox(self, since_timestamp=0, filter_sender_email_list=None):
        return {"mails": list(self.mailbox)}

    def send_mail(self, to, subject, body_text, cc=None, reply_to_mail_id=None,
                  reply_refs_chain=None, reply_all_from=None):
        self._n += 1
        mid = f"<S{self._n}@t>"
        self.sent.append({
            "to": list(to) if isinstance(to, (list, tuple)) else [to],
            "subject": subject, "body": body_text,
            "cc": list(cc) if isinstance(cc, (list, tuple)) else ([cc] if cc else []),
            "mid": mid, "reply_to": reply_to_mail_id,
        })
        return {"success": True, "message_id": mid}

    def mark_seen_by_message_id(self, mid):
        self.seen.append(mid)
        return True


def _mail(mid, frm, body, references="", subject="PRJ001 询价"):
    return {"message_id": mid, "from_email": frm, "to_email_list": [B4],
            "cc_email_list": [], "in_reply_to": references, "references": references,
            "subject": subject, "mail_body_text": body, "body": body}


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    from app.ontology import schema
    monkeypatch.setattr(schema, "ONT_DB_PATH", str(tmp_path / "award.db"))
    ont.init()
    yield


@pytest.fixture()
def gov():
    execution.set_governor(mode="ontology", roll=1.0, exec_enabled=True)
    yield
    execution.set_governor(mode="off", exec_enabled=False)


@pytest.fixture()
def mg(monkeypatch, request):
    """pms 可通过 @pytest.mark.parametrize 间接控制，默认 [PM]。"""
    m = FakeMG()
    pms = getattr(request, "param", PMS)
    monkeypatch.setattr(orbit, "config",
                        lambda: {"suppliers": SUPPLIERS, "approvers": APPROVERS, "pms": pms})
    return m


def _run(mg):
    return orbit.run_full(mg, use_llm=False)


def _collect_quotes(mg):
    """阶段：询价 → 两家报价，返回任务 id。"""
    mg.mailbox += [
        _mail("<Q1@t>", S1, "单价 1000元 货期 3天 全新 数量 2", references="<A@t>"),
        _mail("<Q2@t>", S2, "单价 1200元 货期 5天 原装 数量 2", references="<A@t>"),
    ]
    _run(mg)
    tasks = store.list_tasks()
    assert len(tasks) == 1, tasks
    return tasks[0]["task_id"]


# ── 1. 短语识别 ────────────────────────────────────────────────
@pytest.mark.parametrize("body,want", [
    ("无特殊要求，最低价中标", True),
    ("无特殊要求,最低价中标", True),
    ("无特殊要求 ， 最低价中标", True),
    ("无特殊要求\n最低价中标", True),
    ("无特殊要求，最低价中标；请尽快", True),
    ("本次要求原厂全新并提供质保函", False),
    ("无特殊要求", False),
    ("最低价中标", False),
    ("", False),
])
def test_auto_award_phrase_variants(body, want):
    assert _auto_award(body) is want


def test_parse_inquiry_fields_carries_auto_award():
    assert parse_inquiry_fields(BODY_AUTO)["auto_award"] is True
    assert parse_inquiry_fields(BODY_MANUAL)["auto_award"] is False


# ── 2. 自动轨：直送审批 D ──────────────────────────────────────
def test_auto_track_sends_approval_d(mg, gov):
    mg.mailbox = [_mail("<A@t>", ENG, BODY_AUTO)]
    _run(mg)  # → 发 B
    _collect_quotes(mg)  # → 收集完 → 发 D

    d = next((s for s in mg.sent if "询价汇总" in s["subject"]), None)
    assert d is not None, f"自动轨应发 D 审批汇总，实际发出: {[s['subject'] for s in mg.sent]}"
    assert d["to"] == [ENG]
    assert AP in d["cc"], "D 必须抄送审批人"

    task = store.list_tasks()[0]
    assert task["internal_status"] == "R_APPROVAL"


# ── 3. 人工轨：先发 P 给项目经理 ────────────────────────────────
def test_manual_track_sends_pm_request(mg, gov):
    mg.mailbox = [_mail("<A@t>", ENG, BODY_MANUAL)]
    _run(mg)  # → 发 B
    _collect_quotes(mg)  # → 收集完 → 发 P

    p = next((s for s in mg.sent if "定标请求" in s["subject"]), None)
    assert p is not None, f"人工轨应发 P 定标请求，实际发出: {[s['subject'] for s in mg.sent]}"
    assert p["to"] == [PM], "P 主送必须是项目经理"
    assert AP in p["cc"], "P 必须抄送审批人——否则审批回复脱离线程，任务将永远收不回审批结论"
    assert ENG in p["cc"], "P 应抄送发起人"
    # 不得在人工轨直接发审批汇总 D
    assert not any("询价汇总" in s["subject"] for s in mg.sent), "人工轨不应代发 D 审批汇总"

    task = store.list_tasks()[0]
    assert task["external_status"] == "R_WAIT_PM"


# ── 4. 人工轨：未配置项目经理时留 blocked 审计 ────────────────────
@pytest.mark.parametrize("mg", [[]], indirect=True)
def test_manual_track_without_pm_is_blocked(mg, gov):
    mg.mailbox = [_mail("<A@t>", ENG, BODY_MANUAL)]
    _run(mg)
    _collect_quotes(mg)

    assert not any("定标请求" in s["subject"] for s in mg.sent), "无项目经理时不应发出 P"
    task = store.list_tasks()[0]
    logs = store.list_audit("Task", task["task_id"]) if hasattr(store, "list_audit") else []
    blocked = [x for x in logs if "blocked" in str(x)]
    assert blocked, "未配置项目经理时须留下 blocked 审计，便于运维发现卡单"


# ── 5. 人工轨：审批人在 P 线程内回复 → 下达订货 E ─────────────────
def test_manual_track_approval_reply_triggers_order(mg, gov):
    mg.mailbox = [_mail("<A@t>", ENG, BODY_MANUAL)]
    _run(mg)
    _collect_quotes(mg)

    p = next(s for s in mg.sent if "定标请求" in s["subject"])
    # 审批人在 P 线程内回复（PM 线下比选、特殊要求处理后由其送审批）
    mg.mailbox += [_mail("<AP2@t>", AP, "确认采购", references=p["mid"])]
    _run(mg)

    e = next((s for s in mg.sent if "订货确认" in s["subject"]), None)
    assert e is not None, f"审批通过后应发 E 订货，实际发出: {[s['subject'] for s in mg.sent]}"
    # 人工轨沿用最低价（S1=1000 < S2=1200）
    assert e["to"] == [S1], f"应沿用最低价供应商 {S1}，实际 {e['to']}"


# ── 6. 回归：config() 被简化 mock（缺 pms 键）不得让任务凭空消失 ──
def test_missing_pms_key_does_not_kill_task_creation(monkeypatch, gov):
    """config() 只返回 suppliers/approvers 时，新增键必须用 .get() 取值。

    用下标取会抛 KeyError 并被 claim_inquiries 的宽 except 吞掉，
    症状退化成"任务凭空消失"，极难排查。本测试锁定该回归。
    """
    m = FakeMG()
    monkeypatch.setattr(orbit, "config",
                        lambda: {"suppliers": SUPPLIERS, "approvers": APPROVERS})
    m.mailbox = [_mail("<A@t>", ENG, BODY_MANUAL)]
    _run(m)
    assert len(store.list_tasks()) == 1, "缺少 pms 键也应正常建任务"
