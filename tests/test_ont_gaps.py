# -*- coding: utf-8 -*-
"""NO-012 本体轨遗留缺口修复验证（对应 8 项高风险缺失）。

覆盖：报价结构化解析/upsert幂等/人工改价保护/审批驳回分支/审批显式指定供应商/
线程匹配去坏表达式/超时中止/临期提醒/缺失字段回信/各动作执行器/手动关闭端点。
纯单元 + 轻量集成（FakeMG/TestClient，不触真实 SMTP/IMAP）。
"""
import os
import tempfile
import pytest

os.environ["ONT_DB_PATH"] = tempfile.mktemp(suffix=".db")
import app.ontology as ont
ont.init()
from app.ontology import orbit, execution, store, knowledge
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.ontology import routes as ont_routes

_app = FastAPI()
_app.include_router(ont_routes.router)
_client = TestClient(_app)


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    from app.ontology import schema
    monkeypatch.setattr(schema, "ONT_DB_PATH", str(tmp_path / "gaps.db"))
    ont.init()
    yield


@pytest.fixture()
def gov():
    execution.set_governor(mode="ontology", roll=1.0, exec_enabled=True)
    yield
    execution.set_governor(mode="off", exec_enabled=False)


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
        self.sent.append({"to": to, "subject": subject, "body": body_text,
                          "cc": cc, "mid": mid, "reply_to": reply_to_mail_id})
        return {"success": True, "message_id": mid}

    def mark_seen_by_message_id(self, mid):
        self.seen.append(mid)
        return True


@pytest.fixture()
def mg(monkeypatch):
    m = FakeMG()
    monkeypatch.setattr(orbit, "config", lambda: {
        "suppliers": [{"name": "供A", "email": "s1@x.com"}, {"name": "供B", "email": "s2@x.com"}],
        "approvers": ["ap@x.com"]})
    return m


def _meta_update(task, **kw):
    meta = dict(task.get("spare_info") or {})
    meta.update(kw)
    store.upsert_task({**task, "spare_info": meta})


_MAKE_SEQ = [0]


def _make_task(mg, body_extra=""):
    """建一个字段齐全、已发询价B的本体轨任务，返回 task_id。每次调用 message_id 唯一，便于并发建多个任务。"""
    _MAKE_SEQ[0] += 1
    inquiry = {
        "message_id": f"<A{_MAKE_SEQ[0]}@eng>", "subject": "【备件询价】PRJ-1 硬盘",
        "mail_body_text": ("项目编号：PRJ-1\n项目名称：N\n类型：硬盘\n品牌：Seagate\nPN：ST-1\n"
                           "规格：1T\n成色：全新\n数量：3\n收货地址：addr\n紧急程度：48h" + body_extra),
        "from_email": "eng@x.com", "in_reply_to": "", "references": "",
    }
    mg.mailbox = [inquiry]
    claimed = orbit.claim_inquiries(mg, "ontology", 1.0)
    tid = claimed[0]
    orbit.drive("ontology", use_llm=False, mg=mg)  # 发询价 B
    return tid


def _reply(mg, in_reply_to, sender, body):
    mg._n += 1
    mid = f"<R{mg._n}@{sender.split('@')[0]}>"
    mg.mailbox.append({"message_id": mid, "subject": "Re: X", "mail_body_text": body,
                       "from_email": sender, "in_reply_to": in_reply_to, "references": in_reply_to})
    return mid


# ── 缺口1+2：报价结构化解析 + 同供应商 upsert ──────────────────────────
def test_parse_quote_structured():
    q = orbit._parse_quote("单价：1200元 货期：7天 成色：全新原装 数量：3")
    assert q["unit_price"] == "1200"
    assert "7" in q["delivery"]
    assert q["condition"] == "全新原装"
    assert q["quantity"] == "3"
    # 仅价格（无货期/成色/数量）也应解析出单价
    assert orbit._parse_quote("报价 980")["unit_price"] == "980"
    # 连单价都没有 → None（交由 unparseable 分支催补）
    assert orbit._parse_quote("货期：7天 成色：全新") is None


def test_quote_upsert_no_duplicate(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    b1 = (task["spare_info"].get("b_msg_ids") or [])[0]
    # 同供应商两次报价 → 应 upsert 而非 append
    _reply(mg, b1, "s1@x.com", "单价：1000")
    orbit.process_replies(mg)
    _reply(mg, b1, "s1@x.com", "单价：900")
    orbit.process_replies(mg)
    quotes = store.get_task(tid)["spare_info"]["quotes"]
    s1 = [q for q in quotes if q["email"] == "s1@x.com"]
    assert len(s1) == 1, "同供应商应 upsert 而非 append"
    assert s1[0]["unit_price"] == "900"


# ── 缺口7：人工改价保护 is_manual 不被邮件覆盖 ───────────────────────
def test_manual_quote_not_overwritten(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    b1 = (task["spare_info"].get("b_msg_ids") or [])[0]
    _meta_update(task, quotes=[{"email": "s1@x.com", "unit_price": "888", "is_manual": True, "raw": "manual"}])
    _reply(mg, b1, "s1@x.com", "单价：500")
    orbit.process_replies(mg)
    q = [x for x in store.get_task(tid)["spare_info"]["quotes"] if x["email"] == "s1@x.com"]
    assert len(q) == 1
    assert q[0]["is_manual"] is True and q[0]["unit_price"] == "888"


# ── 缺口5：线程匹配去坏表达式（旧 `or "" in x` 恒真） ───────────────
def test_thread_match_no_false_positive():
    known = {"<B1@x.com>"}
    assert orbit._thread_match("see <B1@x.com> here", known)
    assert orbit._thread_match("<B1@x.com>", known)
    # 不相关邮件不应误匹配（旧实现因 `or "" in x` 恒真会误判）
    assert not orbit._thread_match("一条完全无关的邮件聊聊天气", known)
    assert not orbit._thread_match("", known)


# ── 缺口3：审批驳回分支 → 任务中止 ───────────────────────────────────
def test_approval_reject_aborts(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    _meta_update(task, quotes=[{"email": "s1@x.com", "unit_price": "1000"}], deadline_passed=True)
    orbit.drive("ontology", use_llm=False, mg=mg)  # 发审批 D
    task = store.get_task(tid)
    d_mid = task["spare_info"].get("d_msg_id")
    _reply(mg, d_mid, "ap@x.com", "不同意采购，驳回此单")
    orbit.process_replies(mg)
    assert store.get_task(tid)["spare_info"].get("approval_rejected") is True
    orbit.drive("ontology", use_llm=False, mg=mg)
    fin = store.get_task(tid)
    assert fin["external_status"] == "CLOSED_ABORT"
    assert fin["status"] == "CLOSED"


# ── 缺口4：审批人确认采购沿用最低价；显式点名【其他】供应商才覆盖 ──────────
def test_approval_explicit_supplier(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    _meta_update(task, quotes=[{"email": "s1@x.com", "unit_price": "1000"},
                               {"email": "s2@x.com", "unit_price": "800"}],
                 deadline_passed=True)
    orbit.drive("ontology", use_llm=False, mg=mg)  # 发审批 D
    task = store.get_task(tid)
    d_mid = task["spare_info"].get("d_msg_id")
    # 审批人显名点选更贵的 s1（≠最低价 s2）→ 显式覆盖
    _reply(mg, d_mid, "ap@x.com", "同意采购，就选 s1@x.com 这一家")
    orbit.process_replies(mg)
    sp = store.get_task(tid)["spare_info"]
    assert sp["target_supplier"] == "s1@x.com"
    assert sp["agent_selected_supplier"] == "s2@x.com"  # 智能体固定选最低价 s2


def test_approval_confirm_uses_lowest(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    _meta_update(task, quotes=[{"email": "s1@x.com", "unit_price": "1000"},
                               {"email": "s2@x.com", "unit_price": "800"}],
                 deadline_passed=True)
    orbit.drive("ontology", use_llm=False, mg=mg)  # 发审批 D
    task = store.get_task(tid)
    d_mid = task["spare_info"].get("d_msg_id")
    # 审批人只说「确认采购」，未点名 → 应沿用智能体固定规则的最低价 s2
    _reply(mg, d_mid, "ap@x.com", "确认采购，按比价结果执行即可")
    orbit.process_replies(mg)
    sp = store.get_task(tid)["spare_info"]
    assert sp["target_supplier"] == "s2@x.com", "仅确认采购应沿用智能体最低价"
    assert sp["agent_selected_supplier"] == "s2@x.com"
    # 点名即最低价 s2 → 同样沿用最低价
    tid2 = _make_task(mg)
    task2 = store.get_task(tid2)
    _meta_update(task2, quotes=[{"email": "s1@x.com", "unit_price": "1000"},
                                {"email": "s2@x.com", "unit_price": "800"}],
                 deadline_passed=True)
    orbit.drive("ontology", use_llm=False, mg=mg)
    d2 = store.get_task(tid2)["spare_info"].get("d_msg_id")
    _reply(mg, d2, "ap@x.com", "就选 s2@x.com 这家")
    orbit.process_replies(mg)
    assert store.get_task(tid2)["spare_info"]["target_supplier"] == "s2@x.com"


# ── 缺口6：超时中止（无报价）/ 超时但已有报价走审批 ──────────────────
def test_timeout_abort_no_quotes(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    _meta_update(task, deadline_passed=True, quotes=[])
    orbit.drive("ontology", use_llm=False, mg=mg)
    fin = store.get_task(tid)
    assert fin["external_status"] == "CLOSED_ABORT"


def test_timeout_with_quotes_goes_approval(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    _meta_update(task, deadline_passed=True, quotes=[{"email": "s1@x.com", "unit_price": "1000"}])
    orbit.drive("ontology", use_llm=False, mg=mg)
    fin = store.get_task(tid)
    assert fin["internal_status"] == "R_APPROVAL"


def test_pre_expiry_reminder_sent(mg, gov):
    # 紧急程度 5min → 截止落在 1h 窗口内，且仍有供应商未报价 → 触发临期提醒
    tid = _make_task(mg, body_extra="")
    task = store.get_task(tid)
    _meta_update(task, urgent="5min", quote_deadline=__import__("time").strftime(
        "%Y-%m-%d %H:%M:%S", __import__("time").localtime(__import__("time").time() + 300)))
    orbit.drive("ontology", use_llm=False, mg=mg)
    remind = [s for s in mg.sent if "距报价截止" in s["subject"]]
    assert remind, "截止前窗口应触发临期催报价提醒"


# ── 缺口8：缺失字段回信 + 各动作执行器 ─────────────────────────────
def test_request_missing_fields_sends(mg, gov):
    inquiry = {"message_id": "<A2@eng>", "subject": "【备件询价】缺字段",
               "mail_body_text": ("项目编号：P1\n项目名称：N\n类型：硬盘\n品牌：S\nPN：ST1\n"
                                  "规格：1T\n成色：全新\n数量：3\n紧急程度：48h"),  # 缺收货地址
               "from_email": "eng2@x.com", "in_reply_to": "", "references": ""}
    mg.mailbox = [inquiry]
    claimed = orbit.claim_inquiries(mg, "ontology", 1.0)
    assert claimed
    orbit.drive("ontology", use_llm=False, mg=mg)
    miss = [s for s in mg.sent if "信息不完整" in s["subject"]]
    assert miss, "缺必填字段应回信指出缺失项"
    # 二次驱动不应重复发（missing_requested 去重）
    before = len([s for s in mg.sent if "信息不完整" in s["subject"]])
    orbit.drive("ontology", use_llm=False, mg=mg)
    after = len([s for s in mg.sent if "信息不完整" in s["subject"]])
    assert after == before


def test_noop_actions_have_safe_executors(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    # receiveSupplierQuote / finalizeQuoteCollection 不应再报 noop
    for act in ("receiveSupplierQuote", "finalizeQuoteCollection"):
        ok, _ = execution.execute_action(act, task, {}, mg=mg, force=True)
        assert ok, f"{act} 应安全执行而非 noop"
    # requestTrackingNo：有选中供应商且无单号 → 发索取信（仅一次）
    _meta_update(task, target_supplier="s1@x.com", e_msg_id="<E1@t>")
    ok, _ = execution.execute_action("requestTrackingNo", task, {"target_supplier": "s1@x.com"}, mg=mg, force=True)
    assert ok
    assert [s for s in mg.sent if "快递单号" in s["subject"]]


def test_manual_close_executor_and_endpoint(mg, gov):
    tid = _make_task(mg)
    # 执行器直接关闭
    ok, _ = execution.execute_action("manualCloseTask", store.get_task(tid),
                                     {"operator": "ops", "manual_close_reason": "测试关闭"}, force=True)
    assert ok
    assert store.get_task(tid)["status"] == "CLOSED"
    assert store.get_task(tid)["external_status"] == "CLOSED_MANUAL"
    # 端点关闭（独立建一个任务验证 HTTP 路径）
    tid2 = _make_task(mg)
    r = _client.post(f"/api/ontology-emp009/tasks/{tid2}/close",
                     json={"operator": "ops", "reason": "http关闭"})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert store.get_task(tid2)["external_status"] == "CLOSED_MANUAL"


def test_unparseable_quote_triggers_clarification(mg, gov):
    tid = _make_task(mg)
    task = store.get_task(tid)
    b1 = (task["spare_info"].get("b_msg_ids") or [])[0]
    # 供应商回了一封无法解析出单价的邮件
    _reply(mg, b1, "s1@x.com", "我们已经收到，稍后报价")
    orbit.process_replies(mg)
    assert "s1@x.com" in (store.get_task(tid)["spare_info"].get("unparseable_replies") or [])
    orbit.drive("ontology", use_llm=False, mg=mg)
    assert [s for s in mg.sent if "补充" in s["subject"] or "重发" in s["subject"]], \
        "解析失败应主动回信催补报价"


def test_supplier_display_name_in_summary():
    """供应商实名（中软国际/神州数码）应进入 D 汇总与最低价展示，而非裸邮箱。"""
    from app.ontology import mail_tpl
    task = {
        "task_id": "OT-NAME",
        "spare_info": {
            "project_no": "P1", "project_name": "X",
            "part_type": "硬盘", "brand": "Seagate", "pn": "ST1", "spec": "1TB",
            "condition": "全新", "count": "2", "address": "A", "urgent": "48h",
            "latest_ship_time": "2026-09-30", "quote_deadline": "2026-09-01 00:00",
            "quotes": [
                {"email": "biquanzhi2@163.com", "unit_price": "1280"},
                {"email": "biquanzhi6@163.com", "unit_price": "980"},
            ],
        },
    }
    names = {"biquanzhi2@163.com": "中软国际", "biquanzhi6@163.com": "神州数码"}
    fields = mail_tpl.build_fields({}, task, supplier_names=names)
    assert "中软国际" in fields["suppliers"] and "神州数码" in fields["suppliers"]
    # 最低价应为神州数码（980 < 1280）
    assert fields["lowest_supplier"] == "神州数码"
    # 缺映射时回退裸邮箱（向后兼容）
    fields2 = mail_tpl.build_fields({}, task)
    assert "biquanzhi2@163.com" in fields2["suppliers"]
