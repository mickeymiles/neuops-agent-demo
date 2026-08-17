# -*- coding: utf-8 -*-
"""投标业务域：bid_projects 表（项目元数据 + 拆标报告 JSON + 生成成果 + 自检结果）"""

import json
import time

from .base import (
    _db_lock,
    _get_conn,
    _query_one,
    _query_rows,
)

# 项目流程状态
BID_STATUS_FLOW = ("草稿", "已上传", "已拆标", "已生成", "已自检", "已导出")

# 拆标报告六类
PARSE_SECTIONS = ("qualifications", "performance", "tech_params", "scoring", "rejection_clauses", "response_checklist")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def init_bid_db():
    """初始化投标表结构"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bid_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    tenderee TEXT DEFAULT '',
                    industry TEXT DEFAULT '',
                    budget REAL DEFAULT 0,
                    deadline TEXT DEFAULT '',
                    status TEXT DEFAULT '草稿',
                    parse_report TEXT DEFAULT '{}',
                    generated_docs TEXT DEFAULT '[]',
                    check_result TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bid_status ON bid_projects(status)")
            conn.commit()
        finally:
            conn.close()


# ---------------- 项目 CRUD ----------------

def bid_create_project(name, tenderee="", industry="", budget=0, deadline=""):
    """新建项目，返回项目 dict"""
    now = _now()
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO bid_projects (name, tenderee, industry, budget, deadline, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, '草稿', ?, ?)",
                (name, tenderee, industry, budget or 0, deadline, now, now),
            )
            conn.commit()
            pid = cur.lastrowid
        finally:
            conn.close()
    return bid_get_project(pid)


def bid_list_projects():
    """项目列表（倒序）"""
    rows = _query_rows("SELECT * FROM bid_projects ORDER BY id DESC")
    for r in rows:
        _decode_project(r)
    return rows


def bid_get_project(pid):
    """项目详情"""
    row = _query_one("SELECT * FROM bid_projects WHERE id = ?", (pid,))
    if row:
        _decode_project(row)
    return row


def bid_update_project(pid, **fields):
    """更新项目字段（白名单），返回更新后 dict"""
    allow = {"name", "tenderee", "industry", "budget", "deadline", "status"}
    updates = {k: v for k, v in fields.items() if k in allow}
    if not updates:
        return bid_get_project(pid)
    sets = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [_now(), pid]
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(f"UPDATE bid_projects SET {sets}, updated_at = ? WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()
    return bid_get_project(pid)


def bid_delete_project(pid):
    """删除项目，返回是否删除成功"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute("DELETE FROM bid_projects WHERE id = ?", (pid,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def bid_set_status(pid, status):
    """按流程推进状态（仅在合法流程内前进）"""
    proj = bid_get_project(pid)
    if not proj:
        return None
    cur = proj.get("status", "草稿")
    if status in BID_STATUS_FLOW and status != cur:
        return bid_update_project(pid, status=status)
    return proj


# ---------------- 拆标报告 / 成果 / 自检 ----------------

def bid_save_parse_report(pid, report: dict):
    """保存拆标报告（六类结构化 JSON）"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE bid_projects SET parse_report = ?, updated_at = ? WHERE id = ?",
                (json.dumps(report, ensure_ascii=False), _now(), pid),
            )
            conn.commit()
        finally:
            conn.close()
    return bid_get_project(pid)


def bid_add_generated_doc(pid, doc: dict):
    """追加一条生成成果记录（doc: {id,type,title,path,created_at}）"""
    proj = bid_get_project(pid)
    docs = proj.get("generated_docs") if proj else []
    docs.append(doc)
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE bid_projects SET generated_docs = ?, updated_at = ? WHERE id = ?",
                (json.dumps(docs, ensure_ascii=False), _now(), pid),
            )
            conn.commit()
        finally:
            conn.close()
    return docs


def bid_save_check_result(pid, result: dict):
    """保存合规自检结果"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE bid_projects SET check_result = ?, updated_at = ? WHERE id = ?",
                (json.dumps(result, ensure_ascii=False), _now(), pid),
            )
            conn.commit()
        finally:
            conn.close()
    return bid_get_project(pid)


def _decode_project(row: dict):
    """把 JSON 字段解码为对象（原地修改）"""
    for key in ("parse_report", "generated_docs", "check_result"):
        raw = row.get(key)
        if isinstance(raw, str):
            try:
                row[key] = json.loads(raw) if raw else ({}, [] if key == "generated_docs" else {})
            except Exception:
                row[key] = [] if key == "generated_docs" else {}
        if key == "generated_docs" and row.get(key) is None:
            row[key] = []
