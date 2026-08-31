# -*- coding: utf-8 -*-
"""员工 / 技能域"""

import json
from datetime import datetime

from .base import (
    _db_lock,
    _get_conn,
)

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def db_list_employees() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM employees ORDER BY id").fetchall()
            result = []
            for r in rows:
                e = dict(r)
                e["enabled"] = bool(e.get("enabled", 1))
                try:
                    e["workbench"] = json.loads(e.pop("workbench_json", "") or "null")
                except (TypeError, json.JSONDecodeError):
                    e["workbench"] = None
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
            try:
                e["workbench"] = json.loads(e.pop("workbench_json", "") or "null")
            except (TypeError, json.JSONDecodeError):
                e["workbench"] = None
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
                 "INSERT INTO employees (id, name, desc, type, created, updated, rag_kb, prompt, model, workbench_json, enabled) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, desc=excluded.desc, type=excluded.type, updated=excluded.updated, "
                "rag_kb=excluded.rag_kb, prompt=excluded.prompt, model=excluded.model, "
                 "workbench_json=excluded.workbench_json, enabled=excluded.enabled",
                (emp["id"], emp["name"], emp.get("desc", ""), emp.get("type", ""),
                 emp.get("created", ""), emp.get("updated", ""),
                 emp.get("rag_kb", ""), emp.get("prompt", ""), emp.get("model", ""),
                  json.dumps(emp.get("workbench"), ensure_ascii=False) if emp.get("workbench") else "",
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
    """开关数字员工启用状态（真实生效：运行时 governor 会读取该字段决定员工是否执行）。"""
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


# ── 数字员工「交互方式」配置（邮箱 / 飞书 / 微信 …）──
# 这是智能体作为「一等可管理实体」的核心：每个员工的交互渠道（含凭据）都存库、
# 页面可配，运行时按 (employee_id, channel) 读取，不再依赖 .env / 脚本。

def db_get_employee_channel(emp_id: str, channel: str):
    """读取某员工的单个交互渠道配置。返回 {enabled, config} 或 None。"""
    emp_id, channel = (emp_id or "").strip(), (channel or "").strip()
    if not emp_id or not channel:
        return None
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute(
                "SELECT enabled, config_json FROM employee_channels WHERE employee_id=? AND channel=?",
                (emp_id, channel)).fetchone()
            if not r:
                return None
            cfg = {}
            try:
                cfg = json.loads(r["config_json"] or "{}")
            except Exception:
                cfg = {}
            return {"enabled": bool(r["enabled"]), "config": cfg}
        finally:
            conn.close()


def db_set_employee_channel(emp_id: str, channel: str, enabled: bool, config: dict) -> bool:
    """upsert 某员工的单个交互渠道配置。成功返回 True。"""
    emp_id, channel = (emp_id or "").strip(), (channel or "").strip()
    if not emp_id or not channel:
        return False
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO employee_channels (employee_id, channel, enabled, config_json, updated_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(employee_id, channel) DO UPDATE SET "
                "enabled=excluded.enabled, config_json=excluded.config_json, updated_at=excluded.updated_at",
                (emp_id, channel, 1 if enabled else 0,
                 json.dumps(config if config is not None else {}, ensure_ascii=False), _now()))
            conn.commit()
            return True
        finally:
            conn.close()


def db_list_employee_channels(emp_id: str) -> list:
    """列出某员工的全部交互渠道配置。"""
    emp_id = (emp_id or "").strip()
    if not emp_id:
        return []
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT channel, enabled, config_json FROM employee_channels WHERE employee_id=?",
                (emp_id,)).fetchall()
            out = []
            for r in rows:
                cfg = {}
                try:
                    cfg = json.loads(r["config_json"] or "{}")
                except Exception:
                    cfg = {}
                out.append({"channel": r["channel"], "enabled": bool(r["enabled"]), "config": cfg})
            return out
        finally:
            conn.close()
