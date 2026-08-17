# -*- coding: utf-8 -*-
"""基础设施：SQLite 连接 / 全局锁 / 幂等补列 / 通用查询与统计辅助"""

import json
import sqlite3
import threading

from ..config import DB_PATH

_db_lock = threading.Lock()


def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table, col, ddl):
    """幂等补列：PRAGMA table_info 检查列缺失则 ALTER TABLE ADD COLUMN，保证存量库平滑升级"""
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


_COST_INPUT_PER_M = 2.0


_COST_OUTPUT_PER_M = 3.0


def _query_rows(sql, params=()):
    conn = _get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _query_one(sql, params=()):
    conn = _get_conn()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _est_tokens(text):
    """存量无 token 记录内容的估算：中文约 1.5 字符/token，其他约 4 字符/token"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return int(cjk / 1.5 + (len(text) - cjk) / 4)


def _text_summary(text, limit=120):
    text = (text or "").strip().replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


def _agent_name_map():
    return {a["id"]: a["name"] for a in _query_rows("SELECT id, name FROM employees")}


def _parse_route(route):
    """解析 messages.route 字段：可能是 'emp-004'，也可能是 JSON 字符串 {"employee":"emp-004",...}"""
    s = (route or "").strip()
    if not s:
        return ""
    if s.startswith("{"):
        try:
            j = json.loads(s)
            return str(j.get("employee") or "")
        except Exception:
            return ""
    return s
