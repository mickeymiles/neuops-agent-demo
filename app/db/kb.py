# -*- coding: utf-8 -*-
"""知识库域：KB CRUD / 分块 / 员工绑定"""

from datetime import datetime
import uuid

from .base import (
    _db_lock,
    _get_conn,
    _query_one,
    _query_rows,
)

def db_list_knowledge_bases():
    """列出所有知识库"""
    rows = _query_rows(
        "SELECT * FROM knowledge_bases ORDER BY created_at DESC")
    kbs = []
    for r in rows:
        kb = dict(r)
        kb["employee_ids"] = [e["employee_id"] for e in _query_rows(
            "SELECT employee_id FROM employee_kb WHERE kb_id = ?", (kb["id"],))]
        kbs.append(kb)
    return kbs


def db_get_knowledge_base(kb_id: str):
    row = _query_one("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,))
    if not row:
        return None
    kb = dict(row)
    kb["employee_ids"] = [e["employee_id"] for e in _query_rows(
        "SELECT employee_id FROM employee_kb WHERE kb_id = ?", (kb_id,))]
    return kb


def db_create_knowledge_base(name: str, description: str = "") -> str:
    """新建知识库，返回 kb_id"""
    kb_id = "kb-" + uuid.uuid4().hex[:12]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO knowledge_bases (id, name, description, doc_count, chunk_count, created_at, updated_at) "
                "VALUES (?, ?, ?, 0, 0, ?, ?)",
                (kb_id, name, description, now, now))
            conn.commit()
        finally:
            conn.close()
    return kb_id


def db_rename_knowledge_base(kb_id: str, name: str, description: str = ""):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kb_id))
            conn.commit()
        finally:
            conn.close()


def db_delete_knowledge_base(kb_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
            conn.execute("DELETE FROM knowledge_chunks WHERE kb_id = ?", (kb_id,))
            conn.execute("DELETE FROM employee_kb WHERE kb_id = ?", (kb_id,))
            conn.commit()
        finally:
            conn.close()


def db_update_kb_stats(kb_id: str, doc_count: int, chunk_count: int):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET doc_count = ?, chunk_count = ?, updated_at = ? WHERE id = ?",
                (doc_count, chunk_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kb_id))
            conn.commit()
        finally:
            conn.close()


def db_add_kb_chunks(kb_id: str, doc_name: str, chunks):
    """批量写入切块元数据，返回写入条数"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            for idx, c in enumerate(chunks):
                conn.execute(
                    "INSERT INTO knowledge_chunks (id, kb_id, doc_name, chunk_index, content, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("kc-" + uuid.uuid4().hex[:12], kb_id, doc_name, idx, c,
                     doc_name, now))
            conn.commit()
        finally:
            conn.close()
    return len(chunks)


def db_clear_kb_chunks(kb_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM knowledge_chunks WHERE kb_id = ?", (kb_id,))
            conn.commit()
        finally:
            conn.close()


def db_list_kb_chunks(kb_id: str, offset: int = 0, limit: int = 50):
    rows = _query_rows(
        "SELECT * FROM knowledge_chunks WHERE kb_id = ? ORDER BY created_at DESC, chunk_index ASC LIMIT ? OFFSET ?",
        (kb_id, limit, offset))
    return [dict(r) for r in rows]


def db_count_kb_chunks(kb_id: str) -> int:
    row = _query_one("SELECT COUNT(*) AS n FROM knowledge_chunks WHERE kb_id = ?", (kb_id,))
    return int(row["n"]) if row else 0


def db_delete_kb_chunk(chunk_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM knowledge_chunks WHERE id = ?", (chunk_id,))
            conn.commit()
        finally:
            conn.close()


def db_get_kb_chunk(chunk_id: str):
    row = _query_one("SELECT * FROM knowledge_chunks WHERE id = ?", (chunk_id,))
    return row


def db_bind_employee_kb(employee_id: str, kb_ids):
    """设置员工绑定的知识库（多对多，先清后写）"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM employee_kb WHERE employee_id = ?", (employee_id,))
            for kb_id in kb_ids or []:
                conn.execute(
                    "INSERT OR IGNORE INTO employee_kb (employee_id, kb_id) VALUES (?, ?)",
                    (employee_id, kb_id))
            conn.commit()
        finally:
            conn.close()


def db_get_employee_kb_ids(employee_id: str):
    rows = _query_rows(
        "SELECT kb_id FROM employee_kb WHERE employee_id = ?", (employee_id,))
    return [r["kb_id"] for r in rows]


def db_get_employee_kb_names(employee_id: str):
    rows = _query_rows(
        "SELECT k.name FROM employee_kb ek JOIN knowledge_bases k ON k.id = ek.kb_id "
        "WHERE ek.employee_id = ?", (employee_id,))
    return [r["name"] for r in rows]


def db_get_kb_employees(kb_id: str):
    rows = _query_rows(
        "SELECT e.id, e.name FROM employee_kb ek JOIN employees e ON e.id = ek.employee_id "
        "WHERE ek.kb_id = ?", (kb_id,))
    return [dict(r) for r in rows]
