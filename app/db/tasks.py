# -*- coding: utf-8 -*-
"""任务域：长任务 / 后台任务"""

import json

from .base import (
    _db_lock,
    _get_conn,
)

def db_list_long_tasks() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM long_tasks ORDER BY id").fetchall()
            result = []
            for r in rows:
                t = dict(r)
                t["executions"] = json.loads(t.get("executions") or "[]")
                result.append(t)
            return result
        finally:
            conn.close()


def db_get_long_task(task_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute("SELECT * FROM long_tasks WHERE id=?", (task_id,)).fetchone()
            if not r:
                return None
            t = dict(r)
            t["executions"] = json.loads(t.get("executions") or "[]")
            return t
        finally:
            conn.close()


def db_create_long_task(task: dict):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO long_tasks (id, name, status, description, employee_id, schedule, update_time, executions) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (task["id"], task["name"], task["status"], task.get("description", ""),
                 task.get("employee_id", ""), task.get("schedule", ""), task.get("update_time", ""),
                 json.dumps(task.get("executions", []), ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()


def db_update_long_task(task_id: str, task: dict):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE long_tasks SET name=?, status=?, description=?, employee_id=?, schedule=?, update_time=?, executions=? WHERE id=?",
                (task.get("name", ""), task.get("status", ""), task.get("description", ""),
                 task.get("employee_id", ""), task.get("schedule", ""), task.get("update_time", ""),
                 json.dumps(task.get("executions", []), ensure_ascii=False), task_id),
            )
            conn.commit()
        finally:
            conn.close()


def db_delete_long_task(task_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM long_tasks WHERE id=?", (task_id,))
            conn.commit()
        finally:
            conn.close()


def db_list_bg_tasks() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM bg_tasks ORDER BY id").fetchall()]
        finally:
            conn.close()
