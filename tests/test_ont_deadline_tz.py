# -*- coding: utf-8 -*-
"""emp-009 截止时间时区回归测试。

背景（线上 bug）
──────────────
OT-F5B8364C 询价截止 `quote_deadline = 2026-09-03 00:31:07`（北京时间 GMT+8），
但服务器时钟为 UTC。旧实现：
  - 生成：_inquiry_deadline 用 `datetime.fromtimestamp(...)`（服务器本地=UTC）→ 字符串实为 GMT+8 墙上时间
  - 比较：_deadline_passed 用 `datetime.strptime(dl).timestamp()`（当作本地=UTC）→ 比真实 UTC 晚 8 小时
  → 截止早已过去，deadline_passed 却恒为 False，超时中止（abortTask / 汇总邮件 F）永不触发。

修复：全链路统一以 BIZ_TZ=GMT+8 为基准（生成/解析/基准 epoch 三处一致）。
本用例固定"现在 = 北京时间 2026-09-03 00:39:00"（=UTC 2026-09-02 16:39:00），
验证 GMT+8 生成的过期字符串能正确判定为"已到点"，并触发中止。
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 业务时区（与 orbit.BIZ_TZ / execution.BIZ_TZ 保持一致）
BIZ_TZ = timezone(timedelta(hours=8))

# 固定"现在" = 北京时间 2026-09-03 00:39:00（派生 UTC epoch，避免魔法数字）
_NOW_GMT8 = datetime(2026, 9, 3, 0, 39, 0, tzinfo=BIZ_TZ)
_FIXED_UTC = int(_NOW_GMT8.timestamp())


@pytest.fixture()
def biz(tmp_path, monkeypatch):
    """独立的 9006 业务库 + biz 落库后端（store == store_biz）。"""
    db = str(tmp_path / "proc9006_tz.db")
    import sqlite3
    sqlite3.connect(db).close()
    monkeypatch.setenv("PROC_9006_DB_PATH", db)
    monkeypatch.setenv("ONT_STORE_BACKEND", "biz")
    monkeypatch.delenv("ONT_SETTLEMENT_ENABLED", raising=False)

    from app.ontology import store, execution, decision, orbit
    monkeypatch.setattr(store, "db_path", lambda: db, raising=True)
    monkeypatch.setattr(store, "_schema_ready", False, raising=False)
    assert store.__file__.endswith("store_biz.py"), "默认后端应为 store_biz"
    return store, execution, decision, orbit


def test_deadline_passed_true_for_passed_gmt8(monkeypatch, biz):
    """GMT+8 截止已过 → deadline_passed 必须为 True（修复后）。"""
    store, execution, decision, orbit = biz
    monkeypatch.setattr(orbit.time, "time", lambda: _FIXED_UTC)
    # 北京时间 00:31:07 已过（现在 00:39:00 GMT+8）
    meta = {"quote_deadline": "2026-09-03 00:31:07"}
    assert orbit._deadline_passed(meta) is True


def test_deadline_passed_false_for_future_gmt8(monkeypatch, biz):
    """GMT+8 截止未到 → deadline_passed 必须为 False。"""
    store, execution, decision, orbit = biz
    monkeypatch.setattr(orbit.time, "time", lambda: _FIXED_UTC)
    meta = {"quote_deadline": "2026-09-03 01:00:00"}  # 北京 01:00 还没到
    assert orbit._deadline_passed(meta) is False


def test_deadline_passed_documents_old_bug(monkeypatch, biz):
    """文档化旧实现的 8 小时错位：GMT+8 字符串按 UTC 解析会比实际晚 8 小时。"""
    store, execution, decision, orbit = biz
    monkeypatch.setattr(orbit.time, "time", lambda: _FIXED_UTC)
    dl = "2026-09-03 00:31:07"
    new_epoch = int(datetime.strptime(dl, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BIZ_TZ).timestamp())
    old_epoch_utc = int(datetime.strptime(dl, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    # 旧实现把 GMT+8 字符串当 UTC → epoch 晚 8 小时
    assert new_epoch < old_epoch_utc
    # 修复后：已到点；旧口径：还差 8 小时未到点（这正是线上 bug 的体现）
    assert new_epoch <= _FIXED_UTC < old_epoch_utc
    assert orbit._deadline_passed({"quote_deadline": dl}) is True


def test_inquiry_deadline_generated_as_gmt8(biz):
    """_inquiry_deadline 生成的字符串应为 GMT+8 墙上时间（与解析口径一致）。"""
    store, execution, decision, orbit = biz
    mail = {"date": "Wed, 03 Sep 2026 00:21:37 +0800"}  # 北京时间 00:21:37
    out = orbit._inquiry_deadline(mail, "10min")
    # 00:21:37 + 10min = 北京时间 00:31:37（±解析秒差）
    assert out.startswith("2026-09-03 00:3")


def test_timeout_no_quotes_triggers_abort(biz, monkeypatch):
    """端到端：截止已过且无任何报价 → drive 刷新 deadline_passed 后决策为 abortTask。"""
    store, execution, decision, orbit = biz
    monkeypatch.setattr(orbit.time, "time", lambda: _FIXED_UTC)

    tid = "OT-TZ-ABORT"
    si = {
        "project_no": "PRJ-TZ", "project_name": "测试", "part_type": "硬盘",
        "brand": "Seagate", "pn": "ST-001", "spec": "1TB", "condition": "全新",
        "count": "2", "address": "测试地址", "urgent": "10min",
        "target_supplier": "sup@x.com", "quote_deadline": "2026-09-03 00:31:07",
        "deadline_passed": False, "quotes": [],
    }
    task = {
        "task_id": tid, "mode": "ontology", "status": "INIT",
        "internal_status": "R_INIT", "external_status": "INVITE_QUOTE",
        "from_email": "eng@x.com", "target_supplier": "sup@x.com",
        "create_time": "2026-09-03 00:21:37", "spare_info": si,
    }
    store.upsert_task(task)

    # 复刻 drive() 的截止刷新 + 决策
    t = store.get_task(tid)
    raw = t.get("spare_info") or {}
    meta = json.loads(raw) if isinstance(raw, str) else dict(raw)
    if meta.get("quote_deadline"):
        passed = orbit._deadline_passed(meta)
        meta["deadline_passed"] = passed
        store.upsert_task({**t, "spare_info": meta})
        t = {**t, "spare_info": meta}
    ctx = orbit.ctx_from_task(t)
    aid, ext, inn, reason = decision.propose_action(ctx)
    assert aid == "abortTask", (aid, reason)
    assert ext == "CLOSED_ABORT"
