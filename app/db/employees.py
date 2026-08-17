# -*- coding: utf-8 -*-
"""员工 / 技能域"""

import json

from .base import (
    _db_lock,
    _get_conn,
)

def db_list_employees() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM employees ORDER BY id").fetchall()
            result = []
            for r in rows:
                e = dict(r)
                e["enabled"] = bool(e.get("enabled", 1))
                skill_rows = conn.execute(
                    "SELECT skill_id, enabled FROM employee_skills WHERE employee_id=?",
                    (e["id"],)).fetchall()
                e["skills"] = [x["skill_id"] for x in skill_rows]
                e["skill_states"] = {x["skill_id"]: bool(x["enabled"]) for x in skill_rows}
                e["mcp_tools"] = sorted({x["mcp_id"] for x in conn.execute(
                    "SELECT sm.mcp_id FROM skill_mcp sm "
                    "JOIN employee_skills es ON es.skill_id = sm.skill_id "
                    "WHERE es.employee_id=? AND es.enabled=1", (e["id"],)).fetchall()})
                result.append(e)
            return result
        finally:
            conn.close()


def db_get_employee(emp_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
            if not r:
                return None
            e = dict(r)
            e["enabled"] = bool(e.get("enabled", 1))
            skill_rows = conn.execute(
                "SELECT skill_id, enabled FROM employee_skills WHERE employee_id=?",
                (emp_id,)).fetchall()
            e["skills"] = [x["skill_id"] for x in skill_rows]
            e["skill_states"] = {x["skill_id"]: bool(x["enabled"]) for x in skill_rows}
            e["mcp_tools"] = sorted({x["mcp_id"] for x in conn.execute(
                "SELECT sm.mcp_id FROM skill_mcp sm "
                "JOIN employee_skills es ON es.skill_id = sm.skill_id "
                "WHERE es.employee_id=? AND es.enabled=1", (emp_id,)).fetchall()})
            return e
        finally:
            conn.close()


def db_upsert_employee(emp: dict):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO employees (id, name, desc, type, created, updated, rag_kb, prompt, model, enabled) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, desc=excluded.desc, type=excluded.type, updated=excluded.updated, "
                "rag_kb=excluded.rag_kb, prompt=excluded.prompt, model=excluded.model, "
                "enabled=excluded.enabled",
                (emp["id"], emp["name"], emp.get("desc", ""), emp.get("type", ""),
                 emp.get("created", ""), emp.get("updated", ""),
                 emp.get("rag_kb", ""), emp.get("prompt", ""), emp.get("model", ""),
                 1 if emp.get("enabled", True) else 0),
            )
            # 重建关联（元素可为字符串 id，或 {"id":.., "enabled":..}；缺省启停看 skill_states）
            conn.execute("DELETE FROM employee_skills WHERE employee_id=?", (emp["id"],))
            states = emp.get("skill_states") or {}
            for sid in emp.get("skills", []):
                if isinstance(sid, dict):
                    sid, st = sid.get("id"), sid.get("enabled", True)
                else:
                    st = states.get(sid, True)
                conn.execute(
                    "INSERT OR IGNORE INTO employee_skills (employee_id, skill_id, enabled) VALUES (?,?,?)",
                    (emp["id"], sid, 1 if st else 0))
            conn.commit()
        finally:
            conn.close()


def db_delete_employee(emp_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM employee_skills WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM employees WHERE id=?", (emp_id,))
            conn.commit()
        finally:
            conn.close()


def db_set_employee_skill_enabled(emp_id: str, skill_id: str, enabled: bool):
    """启/停用员工关联技能：保留关联，仅切换生效状态"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO employee_skills (employee_id, skill_id, enabled) VALUES (?,?,?) "
                "ON CONFLICT(employee_id, skill_id) DO UPDATE SET enabled=excluded.enabled",
                (emp_id, skill_id, 1 if enabled else 0))
            conn.commit()
        finally:
            conn.close()


def db_link_employee_skills(emp_id: str, skill_ids: list):
    """为员工批量关联技能（已存在则忽略，默认启用）"""
    if not skill_ids:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            for sid in skill_ids:
                conn.execute(
                    "INSERT INTO employee_skills (employee_id, skill_id, enabled) VALUES (?,?,1) "
                    "ON CONFLICT(employee_id, skill_id) DO NOTHING",
                    (emp_id, sid))
            conn.commit()
        finally:
            conn.close()


def db_unlink_employee_skill(emp_id: str, skill_id: str):
    """解除员工技能关联：彻底移除"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM employee_skills WHERE employee_id=? AND skill_id=?",
                         (emp_id, skill_id))
            conn.commit()
        finally:
            conn.close()


def db_list_skills() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM skills ORDER BY id").fetchall()
            result = []
            for r in rows:
                s = dict(r)
                s["tags"] = json.loads(s.get("tags") or "[]")
                s["enabled"] = bool(s.get("enabled"))
                result.append(s)
            return result
        finally:
            conn.close()


def db_get_skill(skill_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if not r:
                return None
            s = dict(r)
            s["tags"] = json.loads(s.get("tags") or "[]")
            s["enabled"] = bool(s.get("enabled"))
            s["mcp_tools"] = [x["mcp_id"] for x in conn.execute(
                "SELECT mcp_id FROM skill_mcp WHERE skill_id=?", (skill_id,)).fetchall()]
            return s
        finally:
            conn.close()


def db_set_skill_enabled(skill_id: str, enabled: bool):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("UPDATE skills SET enabled=? WHERE id=?", (1 if enabled else 0, skill_id))
            conn.commit()
        finally:
            conn.close()


def db_upsert_skill(skill: dict, tools: list):
    """新增或更新技能：写 skills 表 + 重建 skill_mcp 绑定。
    tools 为绑定的 MCP 工具 id 列表。"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO skills (id, name, desc, category, tags, enabled, prompt, flow, skill_type, `group`) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, desc=excluded.desc, category=excluded.category, "
                "tags=excluded.tags, enabled=excluded.enabled, prompt=excluded.prompt, "
                "flow=excluded.flow, skill_type=excluded.skill_type, `group`=excluded.`group`",
                (skill["id"], skill["name"], skill.get("desc", ""), skill.get("category", ""),
                 json.dumps(skill.get("tags", []), ensure_ascii=False),
                 1 if skill.get("enabled", True) else 0,
                 skill.get("prompt", ""), skill.get("flow", ""), skill.get("skill_type", ""),
                 skill.get("group", "")),
            )
            # 重建技能↔工具绑定
            conn.execute("DELETE FROM skill_mcp WHERE skill_id=?", (skill["id"],))
            for mid in tools or []:
                conn.execute("INSERT OR IGNORE INTO skill_mcp (skill_id, mcp_id) VALUES (?,?)",
                             (skill["id"], mid))
            conn.commit()
        finally:
            conn.close()


def db_delete_skill(skill_id: str):
    """删除技能并级联清理 employee_skills / skill_mcp 绑定"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM employee_skills WHERE skill_id=?", (skill_id,))
            conn.execute("DELETE FROM skill_mcp WHERE skill_id=?", (skill_id,))
            conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
            conn.commit()
        finally:
            conn.close()


def db_set_employee_enabled(emp_id: str, enabled: bool):
    """开关数字员工启用状态（仅监控页展示，不影响主应用路由）"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "UPDATE employees SET enabled=? WHERE id=?",
                (1 if enabled else 0, emp_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
