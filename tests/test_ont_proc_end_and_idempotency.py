# -*- coding: utf-8 -*-
"""emp-009 备件采购：当前版本收口 + 等待态动作幂等（防操作日志刷屏）。

背景
────
1) 业务口径：**供应商发货、拿到快递单号，当前版本流程就结束**——没有收货验收、
   没有结算 G（结算需显式开启 ONT_SETTLEMENT_ENABLED）。终态为
   external=R_PROC_DONE / internal=R_CLOSED / status=CLOSED。

2) 刷屏根因（两层）：
   a. `drive()` 旧判定 `t["status"] in _TERMINAL`，但 _TERMINAL 里全是
      external_status 的枚举，而收口动作写的 status 一律是 "CLOSED"
      → 判断永不命中，已闭环/已中止任务仍被每 60s 反复推进。
   b. 若干"等待态"动作（waitForSupplierShipment / finalizeQuoteCollection /
      processApprovalDecision / requestQuoteClarification / noop 兜底）
      每轮都无条件 store.audit(...) → 页面操作日志每分钟刷一条同名记录。

本用例覆盖上述两类问题，防回归。
"""
import os
import sqlite3
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture()
def biz(tmp_path, monkeypatch):
    """独立的 9006 业务库 + biz 落库后端（store == store_biz）。"""
    db = str(tmp_path / "proc9006_test.db")
    sqlite3.connect(db).close()          # store_biz._connect() 要求库文件已存在
    monkeypatch.setenv("PROC_9006_DB_PATH", db)
    monkeypatch.setenv("ONT_STORE_BACKEND", "biz")
    monkeypatch.delenv("ONT_SETTLEMENT_ENABLED", raising=False)

    from app.ontology import store, execution, decision, orbit
    # db_path() 优先读 app.db.proc_9006_config，测试里强制指向临时库
    monkeypatch.setattr(store, "db_path", lambda: db, raising=True)
    monkeypatch.setattr(store, "_schema_ready", False, raising=False)
    assert store.__file__.endswith("store_biz.py"), "默认后端应为 store_biz"
    return store, execution, decision, orbit


def _base(tid, ext, inn, **si_extra):
    si = {
        "project_no": "PRJ-T", "project_name": "测试", "part_type": "硬盘",
        "brand": "Seagate", "pn": "ST-001", "spec": "1TB", "condition": "全新",
        "count": "2", "address": "测试地址", "urgent": "2h",
        "target_supplier": "sup@x.com", "quote_deadline": "2099-01-01 00:00:00",
    }
    si.update(si_extra)
    return {
        "task_id": tid, "mode": "ontology", "status": "INIT",
        "internal_status": inn, "external_status": ext,
        "from_email": "eng@x.com", "target_supplier": "sup@x.com",
        "create_time": "2026-01-01 00:00:00", "spare_info": si,
    }


class _FakeMG:
    """假邮件网关：只计数不真发（execution 中多个分支要求 mg 非 None）。"""

    def __init__(self):
        self.sent = []

    def send_mail(self, to=None, subject="", body_text="", **kw):
        self.sent.append((tuple(to or []), subject))
        return {"ok": True, "mail_id": "fake-%d" % len(self.sent)}


def _run(biz, tid, rounds=1, mg=None):
    """按 drive() 的真实调用链跑 N 轮，返回 [(action_id, detail), ...]。"""
    store, execution, decision, orbit = biz
    out = []
    for _ in range(rounds):
        t = store.get_task(tid)
        ctx = orbit.ctx_from_task(t)
        aid, *_rest = decision.propose_action(ctx)
        ok, detail = execution.execute_action(aid, t, ctx, mg=mg, force=True)
        out.append((aid, detail))
    return out


def _audit_count(store, tid, action):
    rows = store.list_audit(biz_type="Task", biz_id=tid) or []
    return len([r for r in rows if r.get("action") == action])


# ── 1. 收口：拿到单号 → 登记物流 → 流程结束（终态）─────────────────
def test_tracking_number_completes_procurement(biz):
    store, _execution, _decision, orbit = biz
    tid = "OT-END"
    store.upsert_task(_base(tid, "ORDER_CONFIRM", "R_APPROVAL",
                            tracking_no="SF1234567890"))

    # 轮次1：登记快递单号
    (a1, _d1), = _run(biz, tid)
    t1 = store.get_task(tid)
    assert a1 == "receiveTrackingNumber"
    assert t1["external_status"] == "R_WAIT_SHIPPING"
    # 单号落业务权威列 logistics_no，shipped_no 为只读别名（前端读它）
    assert t1["logistics_no"] == "SF1234567890"
    assert t1["shipped_no"] == "SF1234567890"
    assert t1["task_status"] == "供应商发货中"
    assert not orbit.is_terminal(t1)

    # 轮次2：结算未启用 → 直接收口为终态
    (a2, _d2), = _run(biz, tid)
    t2 = store.get_task(tid)
    assert a2 == "completeProcurement"
    assert t2["external_status"] == "R_PROC_DONE"
    assert t2["internal_status"] == "R_CLOSED"
    assert t2["status"] == "CLOSED"
    assert t2["task_status"] == "流程闭环"
    assert t2["shipped_no"] == "SF1234567890", "收口后单号不应丢失"

    # 终态：drive() / process_replies() 必须跳过
    assert orbit.is_terminal(t2)


def test_terminal_detection_covers_status_and_external(biz):
    """终态判定必须同时看 status 与 external_status（旧实现只看 status → 永不命中）。"""
    _store, _execution, _decision, orbit = biz
    assert orbit.is_terminal({"status": "CLOSED"})
    assert orbit.is_terminal({"external_status": "R_PROC_DONE"})
    assert orbit.is_terminal({"external_status": "CLOSED_ABORT"})
    assert orbit.is_terminal({"external_status": "R_SETTLE"})
    assert not orbit.is_terminal({"status": "INIT", "external_status": "ORDER_CONFIRM"})
    assert not orbit.is_terminal({"status": "INIT", "external_status": "R_WAIT_SHIPPING"})


# ── 2. 等待态动作幂等：多轮轮询不得追加审计 ────────────────────────
@pytest.mark.parametrize("tid,ext,inn,action", [
    ("OT-IDEM-WAIT", "ORDER_CONFIRM", "R_APPROVAL", "waitForSupplierShipment"),
    ("OT-IDEM-COLLECT", "INVITE_QUOTE", "R_INIT", "receiveSupplierQuote"),
    ("OT-IDEM-APPR", "R_DECIDING", "R_INIT", "processApprovalDecision"),
])
def test_waiting_actions_audit_once(biz, tid, ext, inn, action):
    store = biz[0]
    store.upsert_task(_base(tid, ext, inn))
    seen = [a for a, _ in _run(biz, tid, rounds=4, mg=_FakeMG())]
    assert action in seen, f"未命中期望动作 {action}，实际 {set(seen)}"
    n = _audit_count(store, tid, action)
    assert n == 1, f"{action} 审计刷屏：{n} 条（应为 1）"


def test_finalize_logs_once_per_state(biz):
    """兜底 no-op：同一状态只记一次，状态变化后可再记一次。"""
    store = biz[0]
    tid = "OT-IDEM-FINAL"
    # R_PROC_DONE 已是终态，propose 落到兜底分支 finalizeQuoteCollection
    store.upsert_task({**_base(tid, "R_PROC_DONE", "R_CLOSED"), "status": "CLOSED"})
    seen = [a for a, _ in _run(biz, tid, rounds=4)]
    assert seen == ["finalizeQuoteCollection"] * 4
    assert _audit_count(store, tid, "finalizeQuoteCollection") == 1


def test_quote_clarification_sends_and_audits_once(biz):
    """催补报价：发信已去重，但审计此前每轮追加（线上单任务刷出 36 条）。"""
    store = biz[0]
    tid = "OT-IDEM-CLARIFY"
    store.upsert_task(_base(
        tid, "INVITE_QUOTE", "R_INIT",
        suppliers=[{"email": "sup1@x.com", "name": "供1"}],
        quotes=[{"email": "sup1@x.com", "unit_price": "", "delivery": "",
                 "condition": "", "quantity": "", "parse_failed": True}],
        unparseable_replies=["sup1@x.com"],
    ))
    mg = _FakeMG()
    res = _run(biz, tid, rounds=5, mg=mg)
    assert all(a == "requestQuoteClarification" for a, _ in res)
    assert "no executor" not in res[-1][1], "动作未真正执行，用例失去意义"
    assert _audit_count(store, tid, "requestQuoteClarification") == 1
    assert len(mg.sent) == 1, f"催补邮件应只发 1 封，实际 {len(mg.sent)} 封"


def test_noop_fallback_audits_once(biz):
    """无执行器兜底（如邮件网关未就绪）同样不能每轮刷 noop:xxx。"""
    store, execution, _decision, _orbit = biz
    tid = "OT-IDEM-NOOP"
    store.upsert_task(_base(tid, "INVITE_QUOTE", "R_INIT"))
    t = store.get_task(tid)
    for _ in range(4):
        t = store.get_task(tid)
        execution.execute_action("requestQuoteClarification", t, {}, mg=None, force=True)
    assert _audit_count(store, tid, "noop:requestQuoteClarification") == 1


# ── 3. 状态映射：外部流枚举必须对 e 判断 ───────────────────────────
@pytest.mark.parametrize("internal,external,expect", [
    ("R_APPROVAL", "R_WAIT_SHIPPING", "供应商发货中"),
    ("R_CLOSED", "R_PROC_DONE", "流程闭环"),
    ("R_APPROVAL", "ORDER_CONFIRM", "已选型确认"),
    ("R_INIT", "CLOSED_ABORT", "任务已取消"),
    ("R_INIT", "CLOSED_MANUAL", "任务已取消"),
    ("R_INIT", "INVITE_QUOTE", "询比价进行中"),
])
def test_status_mapping(biz, internal, external, expect):
    store = biz[0]
    assert store._task_status(internal, external) == expect
