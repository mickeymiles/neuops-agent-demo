# -*- coding: utf-8 -*-
"""统一探针日志采集器测试：级别解析、增量 tail、ops_logs 落库"""
# 规格编号: NO-001 数据采集（日志采集）
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.probe.base import ProbeReport  # noqa: E402
from app.probe.log_collector import LogCollector, _classify_level, _TailReader  # noqa: E402


def test_classify_level():
    """日志级别解析"""
    assert _classify_level("[ERROR] connect failed") == "error"
    assert _classify_level("CRITICAL: boom") == "critical"
    assert _classify_level("2026-08-15 10:00:00 WARNING disk 90%") == "warn"
    assert _classify_level("INFO request ok") == "info"
    assert _classify_level("plain message") == "info"
    assert _classify_level("DEBUG detail") == "debug"


def test_tail_reader_incremental():
    """增量读取：二次读取只返回新增行"""
    with tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False) as f:
        f.write("line1\nline2\n")
        path = f.name
    try:
        t = _TailReader(path)
        lines = t.read_new_lines(10)
        assert lines == ["line1", "line2"]
        # 追加后只读新增
        with open(path, "a") as f2:
            f2.write("line3\n")
        assert t.read_new_lines(10) == ["line3"]
        assert t.read_new_lines(10) == []
    finally:
        os.unlink(path)


def test_log_collector_collect():
    """采集器输出日志条目 + log 实体 + error 指标"""
    db.init_ops_db()
    with tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False) as f:
        f.write("10:00:01 INFO ok\n")
        f.write("10:00:02 [ERROR] connection refused\n")
        path = f.name
    try:
        db.db_set_setting("app_9007_log", path)
        col = LogCollector()
        rpt = col.collect()
        assert isinstance(rpt, ProbeReport)
        # 日志条目
        msgs = [m for m in rpt.logs if "app:neuops" in m[0]]
        assert len(msgs) == 2
        lv_by_msg = {m[2]: m[1] for m in msgs}
        assert lv_by_msg["10:00:02 [ERROR] connection refused"] == "error"
        # 实体
        ents = [e for e in rpt.entities if e["type"] == "log"]
        assert ents and ents[0]["status"] in ("running", "degraded")
        # 指标（add_metric 元组: entity_type, entity_name, metric, value, unit）
        m_error = [m for m in rpt.metrics if m[2] == "log_error_count"]
        assert m_error and m_error[0][3] == 1.0
    finally:
        os.unlink(path)
        db.db_set_setting("app_9007_log", "")


def test_ops_logs_db_roundtrip():
    """ops_logs 表读写与统计"""
    db.init_ops_db()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    before = db.ops_count_logs(minutes=10, level="error")
    db.ops_save_logs([(now, "app:test", "error", "boom"),
                      (now, "app:test", "info", "ok")])
    rows = db.ops_get_logs(source="app:test", minutes=30)
    assert len(rows) == 2
    assert db.ops_count_logs(minutes=10, level="error") == before + 1
    # 清理测试数据
    with db._db_lock:
        conn = db._get_conn()
        try:
            conn.execute("DELETE FROM ops_logs WHERE source='app:test'")
            conn.commit()
        finally:
            conn.close()
