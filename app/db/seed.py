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
    """将种子员工/技能官方定义同步到库（员工/技能专用的一次性冷启动标记）。

    自 2026-09 起改为「一次性冷启动同步」：首次启动（meta.emp_sync_seeded 未置位）时
    将种子 id 的官方定义补齐/修复到库，并落 emp_sync_seeded 标记；之后重启因标记已存在
    直接跳过，不再覆盖用户通过管理页面维护的定义。

    标记独立于 seed_config_db 的 config_seeded，避免 seed_config_db 先置标而使其失效；
    员工/技能冷启动后改由管理页面或一次性脚本维护。
    仅操作种子 id（MOCK_EMPLOYEES / SKILLS），不触碰用户自建实体。
    """
    if _emp_sync_seeded_set():
        return
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
            # 员工：INSERT OR REPLACE 覆盖官方最新定义（保留用户状态与工作台配置）
            for e in MOCK_EMPLOYEES:
                row = conn.execute(
                    "SELECT enabled, workbench_json FROM employees WHERE id=?", (e["id"],)
                ).fetchone()
                conn.execute(
                    "INSERT OR REPLACE INTO employees (id, name, desc, type, created, updated, rag_kb, prompt, model, workbench_json, enabled) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (e["id"], e["name"], e.get("desc", ""), e.get("type", ""),
                     e.get("created", ""), e.get("updated", ""),
                     e.get("rag_kb", ""), e.get("prompt", ""), e.get("model", ""),
                     row["workbench_json"] if row else "",
                     row["enabled"] if row else 1),
                )
                for sid in e.get("skills", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO employee_skills (employee_id, skill_id) VALUES (?,?)",
                        (e["id"], sid),
                    )
            # ========== 幂等同步 MCP 官方工具（邮件/飞书/表操作/业务解析 11 个） ==========
            # 即使旧库已有 meta.config_seeded=1，也能补进 mcp_tools 表，后台工具中心重启即可见
            try:
                # 确保有 neuops-local 虚拟 server（承载本地 Python 实现的工具）
                conn.execute("""
                    INSERT OR IGNORE INTO mcp_servers (id, name, desc, base_url, enabled, created_at)
                    VALUES ('neuops-local', 'NeuOps 本地 Python 工具集',
                            '承载邮件/飞书/表 CRUD/业务解析等本地 Python 实现的 MCP 工具（无需 MCP Server 网关转发）',
                            'local://python', 1, datetime('now','localtime'))
                """)
            except Exception:
                # mcp_servers 列结构不同或不存在，忽略（兼容更旧的库）
                pass
            # 把 seed_data.MCP_TOOL_SEED 全部幂等写入 mcp_tools（仅 server_id/group 补默认值，不覆盖用户已改的 name/desc）
            from seed_data import MCP_TOOL_SEED as _ALL_TOOLS
            for t in _ALL_TOOLS:
                # INSERT OR IGNORE：若用户已存在同 id 工具，完全不动（保留用户改的 name/desc/group）
                server_id = t.get("server_id", "") or "neuops-local"
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO mcp_tools "
                        "(id, name, desc, icon, tag, danger, category, `group`, server_id, method, path, params_schema) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (t["id"], t["name"], t.get("desc", ""), t.get("icon", ""),
                         t.get("tag", ""), int(t.get("danger", 0)), t.get("category", ""),
                         t.get("group", ""), server_id,
                         t.get("method", "POST"), t.get("path", ""),
                         json.dumps(t.get("params_schema", []), ensure_ascii=False)),
                    )
                except Exception:
                    # 列结构不兼容（老库缺 group/server_id 等列），忽略
                    pass
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('emp_sync_seeded', '1')")
            conn.commit()
        finally:
            conn.close()


def _emp_sync_seeded_set() -> bool:
    """是否已完成员工/技能官方定义冷启动同步（meta.emp_sync_seeded = '1'）"""
    try:
        with _db_lock:
            conn = _get_conn()
            try:
                return bool(conn.execute(
                    "SELECT value FROM meta WHERE key='emp_sync_seeded'"
                ).fetchone())
            finally:
                conn.close()
    except Exception:
        return False


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
                # server_id 尊重 seed_data 里的值（邮件/飞书/表操作/业务解析 11 工具 = neuops-local，
                # 运维/经营/研发等网关工具 = mcp-gateway），只在缺省时回填 mcp-gateway
                server_id = t.get("server_id") or "mcp-gateway"
                # 幂等补回缺失的 seed 工具（如被误删），不覆盖已存在的记录
                conn.execute(
                    "INSERT OR IGNORE INTO mcp_tools "
                    "(id, name, desc, icon, tag, danger, category, server_id, method, path, params_schema) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (t["id"], t["name"], t.get("desc", ""), t.get("icon", "🔧"), t.get("tag", ""),
                     1 if t.get("danger") else 0, t.get("category", ""), server_id,
                     t.get("method", "POST"), t.get("path", ""), params_json),
                )
                # method/path/params_schema 只在为空时回填；server_id 若和 seed 不一致
                #（老库被之前逻辑强制写成 mcp-gateway 的情况），纠正为 seed 里的 server_id
                conn.execute(
                    "UPDATE mcp_tools SET "
                    "server_id=CASE WHEN server_id<>? AND ?<>'mcp-gateway' THEN ? ELSE server_id END, "
                    "method=CASE WHEN method='' OR method IS NULL THEN ? ELSE method END, "
                    "path=CASE WHEN path='' OR path IS NULL THEN ? ELSE path END, "
                    "params_schema=CASE WHEN params_schema='[]' OR params_schema='' OR params_schema IS NULL THEN ? ELSE params_schema END "
                    "WHERE id=?",
                    (server_id, server_id, server_id,
                     t.get("method", "POST"), t.get("path", ""), params_json, t["id"]),
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
