# -*- coding: utf-8 -*-
"""配置种子 + MCP 服务器/工具 CRUD"""

from datetime import datetime
import json

from seed_data import (
    MCP_SERVER_SEED,
    MCP_TOOL_SEED,
    MOCK_BG_TASKS,
    MOCK_EMPLOYEES,
    MOCK_LONG_TASKS,
    MOCK_TODO_HISTORY,
    MOCK_TODOS,
    SKILL_DETAILS,
    SKILLS,
)

from .base import (
    _db_lock,
    _get_conn,
)

def seed_config_db():
    """首次初始化时导入种子数据（meta 标记，仅导入一次，之后重启不再触碰）"""
    with _db_lock:
        conn = _get_conn()
        try:
            if conn.execute("SELECT value FROM meta WHERE key='config_seeded'").fetchone():
                return
            # MCP 工具
            for t in MCP_TOOL_SEED:
                conn.execute(
                    "INSERT OR REPLACE INTO mcp_tools (id, name, desc, icon, tag, danger, category, method, path, params_schema) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (t["id"], t["name"], t["desc"], t["icon"], t["tag"], t["danger"], t["category"],
                     t.get("method", "POST"), t.get("path", ""),
                     json.dumps(t.get("params_schema", []), ensure_ascii=False)),
                )
            # 技能
            for s in SKILLS:
                detail = SKILL_DETAILS.get(s["id"], {})
                conn.execute(
                    "INSERT OR REPLACE INTO skills (id, name, desc, category, tags, enabled, prompt, flow, skill_type) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (s["id"], s["name"], s["desc"], s["category"],
                     json.dumps(s.get("tags", []), ensure_ascii=False),
                     1 if s.get("enabled") else 0,
                     detail.get("prompt", ""), detail.get("flow", ""), detail.get("type", "")),
                )
                for mid in detail.get("tools", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO skill_mcp (skill_id, mcp_id) VALUES (?,?)",
                        (s["id"], mid),
                    )
            # 员工
            for e in MOCK_EMPLOYEES:
                conn.execute(
                    "INSERT OR REPLACE INTO employees (id, name, desc, type, created, updated, rag_kb, prompt, model) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (e["id"], e["name"], e.get("desc", ""), e.get("type", ""),
                     e.get("created", ""), e.get("updated", ""),
                     e.get("rag_kb", ""), e.get("prompt", ""), e.get("model", "")),
                )
                for sid in e.get("skills", []):
                    conn.execute("INSERT OR IGNORE INTO employee_skills (employee_id, skill_id) VALUES (?,?)",
                                 (e["id"], sid))
            # 长期任务
            for t in MOCK_LONG_TASKS:
                conn.execute(
                    "INSERT OR REPLACE INTO long_tasks (id, name, status, description, employee_id, schedule, update_time, executions) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (t["id"], t["name"], t["status"], t.get("description", ""), t.get("employee_id", ""),
                     t.get("schedule", ""), t.get("update_time", ""),
                     json.dumps(t.get("executions", []), ensure_ascii=False)),
                )
            # 待办
            for t in MOCK_TODOS:
                conn.execute(
                    "INSERT OR REPLACE INTO todos (id, type, title, level, time, source_id, auto_skill) VALUES (?,?,?,?,?,?,?)",
                    (t["id"], t["type"], t["title"], t["level"], t["time"], t.get("source_id", ""), t.get("auto_skill", "")),
                )
            # 待办历史
            for t in MOCK_TODO_HISTORY:
                conn.execute(
                    "INSERT OR REPLACE INTO todo_history (id, type, title, level, time, handled_time, result) VALUES (?,?,?,?,?,?,?)",
                    (t["id"], t["type"], t["title"], t["level"], t["time"], t.get("handled_time", ""), t.get("result", "")),
                )
            # 后台任务
            for t in MOCK_BG_TASKS:
                conn.execute(
                    "INSERT OR REPLACE INTO bg_tasks (id, name, status, desc) VALUES (?,?,?,?)",
                    (t["id"], t["name"], t["status"], t.get("desc", "")),
                )
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('config_seeded', '1')")
            conn.commit()
        finally:
            conn.close()


def sync_seed_employees():
    """每次启动调用：将种子员工/技能官方定义幂等同步到库。

    与 seed_config_db（仅首次导入，meta.config_seeded 标记后不再触碰）不同，
    本函数始终覆盖种子 id 的官方定义，用于：
    1) 新增员工/技能落库：emp-006/007、skill-20/21（本次 7 大数字员工实装）；
    2) 修复官方定义已变更的种子实体：emp-005「必选+有限规则配置修改+人工确认」、
       skill-13「9006规则配置辅助」等旧库残留定义；
    3) 仅操作种子 id（MOCK_EMPLOYEES / SKILLS），不触碰用户自建实体；
       保留既有 enabled 启停状态，不重置用户对种子员工的启停控制。
    """
    with _db_lock:
        conn = _get_conn()
        try:
            # 技能：INSERT OR REPLACE 覆盖官方最新定义（含 prompt/flow/skill_type/tags）
            for s in SKILLS:
                detail = SKILL_DETAILS.get(s["id"], {})
                row = conn.execute("SELECT enabled FROM skills WHERE id=?", (s["id"],)).fetchone()
                conn.execute(
                    "INSERT OR REPLACE INTO skills (id, name, desc, category, tags, enabled, prompt, flow, skill_type) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (s["id"], s["name"], s["desc"], s["category"],
                     json.dumps(s.get("tags", []), ensure_ascii=False),
                     row["enabled"] if row else (1 if s.get("enabled") else 0),
                     detail.get("prompt", ""), detail.get("flow", ""), detail.get("type", "")),
                )
                for mid in detail.get("tools", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO skill_mcp (skill_id, mcp_id) VALUES (?,?)",
                        (s["id"], mid),
                    )
            # 员工：INSERT OR REPLACE 覆盖官方最新定义（保留 enabled 启停状态）
            for e in MOCK_EMPLOYEES:
                row = conn.execute("SELECT enabled FROM employees WHERE id=?", (e["id"],)).fetchone()
                conn.execute(
                    "INSERT OR REPLACE INTO employees (id, name, desc, type, created, updated, rag_kb, prompt, model, enabled) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (e["id"], e["name"], e.get("desc", ""), e.get("type", ""),
                     e.get("created", ""), e.get("updated", ""),
                     e.get("rag_kb", ""), e.get("prompt", ""), e.get("model", ""),
                     row["enabled"] if row else 1),
                )
                for sid in e.get("skills", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO employee_skills (employee_id, skill_id) VALUES (?,?)",
                        (e["id"], sid),
                    )
            conn.commit()
        finally:
            conn.close()


def ensure_mcp_server_mapping():
    """幂等回填 MCP Server 归属：每次启动调用。
    1) INSERT OR IGNORE 导入 mcp_servers 实体（MCP_SERVER_SEED）
    2) 仅当 server_id 为空时，将 mcp_tools 统一归属到 mcp-gateway，保证已有线上库正确建边
    3) 用 MCP_TOOL_SEED 补全新列 method/path/params_schema（仅当为空时），保证旧库工具定义完整
    4) 用 SKILL_DETAILS 幂等补回 skill_mcp 绑定（仅当缺失时），保证旧库技能↔工具关系完整
    """
    with _db_lock:
        conn = _get_conn()
        try:
            for s in MCP_SERVER_SEED:
                conn.execute(
                    "INSERT OR IGNORE INTO mcp_servers (id, name, desc, base_url, type, auth, status, last_sync) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (s["id"], s["name"], s.get("desc", ""), s.get("base_url", ""),
                     s.get("type", "gateway"), s.get("auth", ""),
                     s.get("status", "online"), s.get("last_sync", "")),
                )
            conn.execute(
                "UPDATE mcp_tools SET server_id='mcp-gateway' WHERE server_id IS NULL OR server_id=''"
            )
            for t in MCP_TOOL_SEED:
                params_json = json.dumps(t.get("params_schema", []), ensure_ascii=False)
                # 幂等补回缺失的 seed 工具（如被误删），不覆盖已存在的记录
                conn.execute(
                    "INSERT OR IGNORE INTO mcp_tools "
                    "(id, name, desc, icon, tag, danger, category, server_id, method, path, params_schema) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (t["id"], t["name"], t["desc"], t.get("icon", "🔧"), t.get("tag", ""),
                     1 if t.get("danger") else 0, t.get("category", ""), "mcp-gateway",
                     t.get("method", "POST"), t.get("path", ""), params_json),
                )
                conn.execute(
                    "UPDATE mcp_tools SET "
                    "method=CASE WHEN method='' OR method IS NULL THEN ? ELSE method END, "
                    "path=CASE WHEN path='' OR path IS NULL THEN ? ELSE path END, "
                    "params_schema=CASE WHEN params_schema='[]' OR params_schema='' OR params_schema IS NULL THEN ? ELSE params_schema END "
                    "WHERE id=?",
                    (t.get("method", "POST"), t.get("path", ""), params_json, t["id"]),
                )
            # 幂等补回 seed 技能的 skill_mcp 绑定（仅缺失时），兼容旧库
            for s in SKILLS:
                detail = SKILL_DETAILS.get(s["id"], {})
                for mid in detail.get("tools", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO skill_mcp (skill_id, mcp_id) VALUES (?,?)",
                        (s["id"], mid),
                    )
            conn.commit()
        finally:
            conn.close()


# ═══════════════════════════════════════════
# MCP Server / MCP 工具 CRUD
# ═══════════════════════════════════════════


def db_list_mcp_servers() -> list:
    """列出全部 MCP Server，附带各自工具数"""
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM mcp_servers ORDER BY id").fetchall()
            result = []
            for r in rows:
                s = dict(r)
                s["tool_count"] = conn.execute(
                    "SELECT COUNT(*) c FROM mcp_tools WHERE server_id=?", (s["id"],)
                ).fetchone()["c"]
                result.append(s)
            return result
        finally:
            conn.close()


def db_get_mcp_server(server_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()


def db_upsert_mcp_server(server: dict):
    """新增或更新 MCP Server。id 由调用方生成（新增时），更新时按 id 覆盖。"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO mcp_servers (id, name, desc, base_url, type, auth, status, last_sync, `group`) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, desc=excluded.desc, base_url=excluded.base_url, "
                "type=excluded.type, auth=excluded.auth, status=excluded.status, last_sync=excluded.last_sync, "
                "`group`=excluded.`group`",
                (server["id"], server["name"], server.get("desc", ""), server.get("base_url", ""),
                 server.get("type", "gateway"), server.get("auth", ""),
                 server.get("status", "online"), server.get("last_sync", ""),
                 server.get("group", "")),
            )
            conn.commit()
        finally:
            conn.close()


def db_delete_mcp_server(server_id: str):
    """删除 MCP Server 并级联删除其下工具及技能绑定"""
    with _db_lock:
        conn = _get_conn()
        try:
            tool_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM mcp_tools WHERE server_id=?", (server_id,)).fetchall()]
            for tid in tool_ids:
                conn.execute("DELETE FROM skill_mcp WHERE mcp_id=?", (tid,))
            conn.execute("DELETE FROM mcp_tools WHERE server_id=?", (server_id,))
            conn.execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
            conn.commit()
        finally:
            conn.close()


def db_sync_server_tools(server_id: str, tools: list) -> int:
    """把从 MCP Server /tools 发现端点拉取的工具写入 mcp_tools（幂等）。
    tools 元素支持两种格式：
      - {"name","method","desc","params":[参数名...]}（mcp-gateway 风格）
      - {"id"/"name","method","desc","params_schema":[{name,type,required,desc}], "path"}
    返回写入/更新的工具数。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    with _db_lock:
        conn = _get_conn()
        try:
            srv = conn.execute("SELECT `group` FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
            srv_group = (srv["group"] if srv else "") or ""
            for t in tools:
                tid = t.get("id") or t.get("name")
                if not tid:
                    continue
                # 归一化 params：gateway 风格只给参数名，转成 schema
                params = t.get("params_schema")
                if params is None and t.get("params"):
                    params = []
                    for p in t["params"]:
                        if isinstance(p, dict):
                            params.append(p)
                        else:
                            params.append({"name": str(p), "type": "string",
                                           "required": False, "desc": ""})
                path = t.get("path", "")
                if not path:
                    path = f"/tools/{tid}"
                # 工具 id 跨 server 冲突保护：若该 id 已属于其他 server，
                # 用 {server_id}:{tid} 作为本 server 的独立工具 id，避免覆盖/误删他人工具
                row = conn.execute("SELECT server_id FROM mcp_tools WHERE id=?", (tid,)).fetchone()
                if row and row["server_id"] != server_id:
                    tid = f"{server_id}:{tid}"
                # 注意：ON CONFLICT UPDATE 刻意不更新 `group`，
                # 避免同步覆盖管理端手工设置的业务分组；仅新建工具继承 Server 分组
                conn.execute(
                    "INSERT INTO mcp_tools (id, name, desc, icon, tag, danger, category, `group`, server_id, method, path, params_schema) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "name=excluded.name, desc=excluded.desc, server_id=excluded.server_id, "
                    "method=excluded.method, path=excluded.path, params_schema=excluded.params_schema",
                    (tid, t.get("name") or tid, t.get("desc", ""), t.get("icon", "🔧"),
                     t.get("tag", ""), 1 if t.get("danger") else 0, t.get("category", ""),
                     srv_group,
                     server_id, t.get("method", "POST"), path,
                     json.dumps(params or [], ensure_ascii=False)),
                )
                count += 1
            conn.execute("UPDATE mcp_servers SET last_sync=? WHERE id=?", (now, server_id))
            conn.commit()
        finally:
            conn.close()
    return count


def db_list_mcp_tools(server_id: str = "") -> list:
    """列出 MCP 工具；server_id 非空时按服务器过滤"""
    with _db_lock:
        conn = _get_conn()
        try:
            if server_id:
                rows = conn.execute(
                    "SELECT * FROM mcp_tools WHERE server_id=? ORDER BY id", (server_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM mcp_tools ORDER BY id").fetchall()
            result = []
            for r in rows:
                t = dict(r)
                try:
                    t["params_schema"] = json.loads(t.get("params_schema") or "[]")
                except Exception:
                    t["params_schema"] = []
                if t.get("server_id"):
                    sv = conn.execute("SELECT name FROM mcp_servers WHERE id=?", (t["server_id"],)).fetchone()
                    t["server_name"] = sv["name"] if sv else ""
                result.append(t)
            return result
        finally:
            conn.close()


def db_get_mcp_tool(tool_id: str):
    with _db_lock:
        conn = _get_conn()
        try:
            r = conn.execute("SELECT * FROM mcp_tools WHERE id=?", (tool_id,)).fetchone()
            if not r:
                return None
            t = dict(r)
            try:
                t["params_schema"] = json.loads(t.get("params_schema") or "[]")
            except Exception:
                t["params_schema"] = []
            return t
        finally:
            conn.close()


def db_update_mcp_tool(tool_id: str, fields: dict) -> bool:
    """按需更新 MCP 工具字段（当前仅用于调整业务分组 group），返回是否命中记录"""
    allowed = {"group", "name", "desc", "tag", "category"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"`{k}`=?")
            params.append(v)
    if not sets:
        return False
    params.append(tool_id)
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                f"UPDATE mcp_tools SET {', '.join(sets)} WHERE id=?",
                params,
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
