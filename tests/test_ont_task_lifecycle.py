# -*- coding: utf-8 -*-
"""任务生命周期收口测试：页面取消 → 智能体终态（防僵尸任务）。

背景：9006「取消任务」只 UPDATE `procurement_task.task_status='任务已取消'`，
不动 `status` / `external_status`。此前 `is_terminal()` 只看后两者，导致
"页面已取消、智能体还在每 60s 推进"的僵尸任务。

覆盖：
- is_terminal 认页面侧 task_status
- reclaim_canceled 把已取消但未置终态的任务补齐收口（manualCloseTask + force）
- store_biz._resolve_task_status 不得把页面终态冲回"进行中"
"""
import os
import tempfile

_tmpdb = tempfile.mktemp(suffix=".db")
os.environ.setdefault("ONT_DB_PATH", _tmpdb)
os.environ.setdefault("PROC_9006_DB_PATH", _tmpdb)

from app.ontology import orbit, store_biz


# ── is_terminal：页面侧终态必须被认可 ────────────────────────────────
def test_terminal_by_page_cancel():
    # 页面取消只写 task_status，智能体两个状态列仍停在"进行中"
    t = {"task_id": "OT-1", "status": "INIT", "external_status": "ORDER_CONFIRM",
         "internal_status": "R_APPROVAL", "task_status": "任务已取消"}
    assert orbit.is_terminal(t) is True


def test_terminal_by_page_closed():
    assert orbit.is_terminal({"status": "INIT", "external_status": "R_DECIDING",
                              "task_status": "流程闭环"}) is True


def test_not_terminal_when_running():
    assert orbit.is_terminal({"status": "INIT", "external_status": "INVITE_QUOTE",
                              "task_status": "询比价进行中"}) is False


def test_terminal_legacy_closed_status():
    assert orbit.is_terminal({"status": "CLOSED", "external_status": "CLOSED_ABORT"}) is True


# ── reclaim_canceled：只收口"已取消但未置终态"的任务 ──────────────────
def test_reclaim_canceled_closes_task(monkeypatch):
    tasks = [
        {"task_id": "OT-CANCEL", "status": "INIT", "external_status": "ORDER_CONFIRM",
         "task_status": "任务已取消", "cancel_reason": "测试取消"},
        {"task_id": "OT-RUN", "status": "INIT", "external_status": "INVITE_QUOTE",
         "task_status": "询比价进行中"},
    ]
    monkeypatch.setattr(orbit.store, "list_tasks", lambda limit=200: tasks)
    called = []

    def _fake_exec(action_id, task, ctx, mg=None, force=False):
        called.append((action_id, task["task_id"], ctx.get("manual_close_reason"), force))
        return True, "ok"

    monkeypatch.setattr(orbit.execution, "execute_action", _fake_exec)

    done = orbit.reclaim_canceled()
    assert [d["task_id"] for d in done] == ["OT-CANCEL"], "只收口页面已取消的任务"
    assert called[0][0] == "manualCloseTask"
    assert called[0][2] == "测试取消", "取消原因应带入审计"
    assert called[0][3] is True, "人工取消必须 force，不受 governor 灰度限制"


def test_reclaim_canceled_skips_already_terminal(monkeypatch):
    tasks = [{"task_id": "OT-DONE", "status": "CLOSED",
              "external_status": "CLOSED_MANUAL", "task_status": "任务已取消"}]
    monkeypatch.setattr(orbit.store, "list_tasks", lambda limit=200: tasks)

    def _boom(*a, **k):
        raise AssertionError("已终态的任务不应重复收口")

    monkeypatch.setattr(orbit.execution, "execute_action", _boom)
    assert orbit.reclaim_canceled() == []


def test_reclaim_canceled_tolerates_failure(monkeypatch):
    tasks = [{"task_id": "OT-ERR", "status": "INIT", "external_status": "ORDER_CONFIRM",
              "task_status": "任务已取消"}]
    monkeypatch.setattr(orbit.store, "list_tasks", lambda limit=200: tasks)

    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(orbit.execution, "execute_action", _boom)
    done = orbit.reclaim_canceled()
    assert len(done) == 1 and done[0]["ok"] is False, "单个任务收口失败不应中断整轮"


# ── _resolve_task_status：页面终态不被智能体重算覆盖 ──────────────────
def test_resolve_task_status_keeps_page_terminal():
    t = {"task_status": "任务已取消", "internal_status": "R_APPROVAL",
         "external_status": "ORDER_CONFIRM"}
    assert store_biz._resolve_task_status(t) == "任务已取消"
    assert store_biz._resolve_task_status({**t, "task_status": "流程闭环"}) == "流程闭环"


def test_resolve_task_status_recomputes_when_active():
    t = {"task_status": "询比价进行中", "internal_status": "R_APPROVAL",
         "external_status": "ORDER_CONFIRM"}
    assert store_biz._resolve_task_status(t) == "已选型确认"
