# -*- coding: utf-8 -*-
"""「备件邮件询价」数字员工数据层：仅 spare_mail_task 任务 CRUD。

模板、采购邮箱、审批人邮箱、启停开关等静态配置统一迁移到 skill JSON
（skills/skill-proc-mail-inquiry.json）。本文件只负责动态运行态任务表的读写。
"""
from datetime import datetime
from typing import Optional

from .base import (
    _db_lock,
    _get_conn,
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 表字段集合（与 schema.py 的 CREATE TABLE 保持同步）
_TASK_COLS = (
    "task_id", "thread_msg_id", "approver_email",
    "project_no", "project_name", "part_type", "brand", "pn", "spec",
    "condition", "count", "address", "inquiry_dur", "latest_ship_time",
    "inquiry_deadline", "suppliers_json", "quotes_json", "lowest_supplier",
    "lowest_quote", "approval_state", "approval_result", "target_supplier",
    "status", "latest_step", "created_at", "updated_at",
)


def spare_mail_create_task(task: dict) -> str:
    """新建/upsert 任务，返回 task_id。
    task_id 必填；缺省字段填空串，时间戳自动补齐。
    """
    tid = str((task or {}).get("task_id") or "").strip()
    if not tid:
        raise ValueError("task_id 必填")
    now = _now()
    data = {k: (task or {}).get(k, "") for k in _TASK_COLS}
    data["task_id"] = tid
    data["created_at"] = data["created_at"] or now
    data["updated_at"] = now
    with _db_lock:
        conn = _get_conn()
        try:
            keys = list(data.keys())
            ph = ",".join(["?"] * len(keys))
            sets = ",".join([f"{c}=excluded.{c}" for c in _TASK_COLS if c != "task_id"])
            conn.execute(
                f"INSERT INTO spare_mail_task ({','.join(keys)}) VALUES ({ph}) "
                f"ON CONFLICT(task_id) DO UPDATE SET {sets}",
                list(data.values())
            )
            conn.commit()
        finally:
            conn.close()
    return tid


def spare_mail_get_task(task_id: str) -> Optional[dict]:
    """按 task_id 取单条任务；不存在返回 None。"""
    task_id = str(task_id or "").strip()
    if not task_id:
        return None
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute(
                "SELECT * FROM spare_mail_task WHERE task_id=?", (task_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()


def spare_mail_list_tasks(filter: Optional[dict] = None, page_size: int = 100) -> list:
    """任务列表。filter 支持 status / keyword 键；keyword 会对
    project_name/pn/lowest_supplier/target_supplier 做模糊匹配。
    """
    filter = filter or {}
    with _db_lock:
        conn = _get_conn()
        try:
            sql = "SELECT * FROM spare_mail_task WHERE 1=1"
            params = []
            status = filter.get("status")
            if status:
                sql += " AND status=?"
                params.append(status)
            kw = (filter.get("keyword") or "").strip()
            if kw:
                like = f"%{kw}%"
                sql += (" AND (project_name LIKE ? OR pn LIKE ?"
                        " OR lowest_supplier LIKE ? OR target_supplier LIKE ?)")
                params.extend([like, like, like, like])
            sql += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, int(page_size)))
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()


def spare_mail_update_task(task_id: str, patch: dict) -> int:
    """更新任务部分字段（自动过滤未知列）。返回受影响行数。"""
    task_id = str(task_id or "").strip()
    if not task_id:
        return 0
    safe = {k: v for k, v in (patch or {}).items()
            if k in _TASK_COLS and k != "task_id"}
    if not safe:
        return 0
    safe["updated_at"] = _now()
    with _db_lock:
        conn = _get_conn()
        try:
            sets = ",".join([f"{c}=?" for c in safe.keys()])
            cur = conn.execute(
                f"UPDATE spare_mail_task SET {sets} WHERE task_id=?",
                list(safe.values()) + [task_id]
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
