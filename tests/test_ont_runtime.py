# -*- coding: utf-8 -*-
"""emp-009 本体轨调度运行时测试：页面开关即时拉起 / 停止监听线程。

验证：
- should_run() 受 ONT_SCHEDULER 总闸 + execution.needs_exec()(含页面 enabled) 控制；
- sync_scheduler() 幂等：启用→创建 task，停用→取消并清空 task。
"""
import os
import asyncio
import tempfile

os.environ.setdefault("ONT_DB_PATH", tempfile.mktemp(suffix=".db"))

import app.ontology as ont
ont.init()
from app.ontology import runtime, execution


def test_should_run_gated_by_master_switch_and_needs_exec(monkeypatch):
    monkeypatch.setattr(execution, "needs_exec", lambda: True)
    # 总闸关 → 即便 needs_exec 通过也不起
    monkeypatch.setenv("ONT_SCHEDULER", "0")
    assert runtime.should_run() is False
    # 总闸开 + needs_exec True → 起
    monkeypatch.setenv("ONT_SCHEDULER", "1")
    assert runtime.should_run() is True
    # 总闸开 + needs_exec False（页面停用）→ 不起
    monkeypatch.setattr(execution, "needs_exec", lambda: False)
    assert runtime.should_run() is False


def test_sync_scheduler_creates_and_stops_task(monkeypatch):
    monkeypatch.setenv("ONT_SCHEDULER", "1")
    monkeypatch.setattr(execution, "needs_exec", lambda: True)
    runtime._ont_task = None

    async def run():
        # 启用 → 应拉起 task
        await runtime.sync_scheduler()
        assert runtime._ont_task is not None and not runtime._ont_task.done()
        # 停用 → 应取消并清空 task
        monkeypatch.setattr(execution, "needs_exec", lambda: False)
        await runtime.sync_scheduler()
        try:
            await runtime._ont_task
        except Exception:
            pass
        assert runtime._ont_task is None

    asyncio.run(run())
    runtime._ont_task = None
