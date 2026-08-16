# -*- coding: utf-8 -*-
"""SQLite 数据层：连接 / 建表 / 种子数据 / 通用查询封装"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime

from seed_data import (
    MCP_SERVER_SEED,
    MCP_TOOL_SEED,
    MOCK_BG_TASKS,
    MOCK_CONV_MESSAGES,
    MOCK_EMPLOYEES,
    MOCK_LONG_TASKS,
    MOCK_TODO_HISTORY,
    MOCK_TODOS,
    SKILL_DETAILS,
    SKILLS,
)

from .config import DB_PATH

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


def init_session_db():
    """初始化会话库表结构"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    thought TEXT DEFAULT '',
                    tools TEXT DEFAULT '[]',
                    conclusion TEXT DEFAULT '',
                    route TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id)")
            # 项目表（会话分组）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # 兼容旧库：为 conversations 补 project_id / pinned / share_id 列
            conv_cols = [r["name"] for r in conn.execute("PRAGMA table_info(conversations)")]
            if "project_id" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT DEFAULT ''")
            # DSH 内核引擎观测字段（P3）：会话使用的引擎 + DSH session id
            _ensure_column(conn, "conversations", "engine", "TEXT DEFAULT 'legacy'")
            _ensure_column(conn, "conversations", "dsh_session_id", "TEXT DEFAULT ''")
            if "pinned" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER DEFAULT 0")
            if "share_id" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN share_id TEXT DEFAULT ''")
            # LLM 调用观测表（Langfuse 式 trace：记录每次模型调用的 token/耗时/内容/成本）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT DEFAULT '',
                    employee_id TEXT DEFAULT '',
                    employee_name TEXT DEFAULT '',
                    stage TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    latency_ms INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    input TEXT DEFAULT '',
                    output TEXT DEFAULT '',
                    temperature REAL DEFAULT 0,
                    max_tokens INTEGER DEFAULT 0,
                    round_no INTEGER DEFAULT 0,
                    tool_names TEXT DEFAULT '',
                    cost REAL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_conv ON llm_calls(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_emp ON llm_calls(employee_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_time ON llm_calls(created_at)")
            # 兼容旧库：为已存在的 llm_calls 表补列（幂等）
            for _col, _ddl in (
                ("error", "TEXT DEFAULT ''"),
                ("input", "TEXT DEFAULT ''"),
                ("output", "TEXT DEFAULT ''"),
                ("temperature", "REAL DEFAULT 0"),
                ("max_tokens", "INTEGER DEFAULT 0"),
                ("round_no", "INTEGER DEFAULT 0"),
                ("tool_names", "TEXT DEFAULT ''"),
                ("cost", "REAL DEFAULT 0"),
            ):
                _ensure_column(conn, "llm_calls", _col, _ddl)
            # 工具调用观测表：记录 Agent 循环中每次 MCP 工具调用的入参/出参/耗时/成败
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT DEFAULT '',
                    employee_id TEXT DEFAULT '',
                    employee_name TEXT DEFAULT '',
                    round_no INTEGER DEFAULT 0,
                    function_name TEXT DEFAULT '',
                    args TEXT DEFAULT '',
                    result TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    error TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_conv ON tool_calls(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_time ON tool_calls(created_at)")
            # RAG 检索观测表：记录知识库检索的 query / 命中数 / 相似度 / 来源
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_retrievals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT DEFAULT '',
                    employee_id TEXT DEFAULT '',
                    employee_name TEXT DEFAULT '',
                    query TEXT DEFAULT '',
                    hit_count INTEGER DEFAULT 0,
                    top_score REAL DEFAULT 0,
                    min_score REAL DEFAULT 0,
                    sources TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_conv ON rag_retrievals(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_time ON rag_retrievals(created_at)")
            # 告警规则表（可配置：指标 / 阈值 / 窗口 / 严重级别）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    target TEXT DEFAULT '',
                    threshold REAL DEFAULT 0,
                    window_min INTEGER DEFAULT 60,
                    severity TEXT DEFAULT 'warning',
                    enabled INTEGER DEFAULT 1,
                    desc TEXT DEFAULT ''
                )
            """)
            # 告警记录表（业务视角：智能体 APM 告警中心）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id TEXT DEFAULT '',
                    rule_name TEXT DEFAULT '',
                    severity TEXT DEFAULT 'warning',
                    metric TEXT DEFAULT '',
                    target TEXT DEFAULT '',
                    target_name TEXT DEFAULT '',
                    status TEXT DEFAULT 'firing',
                    message TEXT DEFAULT '',
                    value REAL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_status ON alerts(status)")
            conn.commit()
        finally:
            conn.close()


def init_config_db():
    """初始化数字员工/技能/MCP工具 配置库表结构"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    desc TEXT DEFAULT '',
                    type TEXT DEFAULT '',
                    created TEXT DEFAULT '',
                    updated TEXT DEFAULT '',
                    rag_kb TEXT DEFAULT '',
                    prompt TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1
                )
            """)
            # 兼容旧库：为已存在的 employees 表补 enabled 列（默认启用）
            try:
                emp_cols = [r["name"] for r in conn.execute("PRAGMA table_info(employees)")]
                if "enabled" not in emp_cols:
                    conn.execute("ALTER TABLE employees ADD COLUMN enabled INTEGER DEFAULT 1")
            except Exception:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    desc TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    enabled INTEGER DEFAULT 1,
                    prompt TEXT DEFAULT '',
                    flow TEXT DEFAULT '',
                    skill_type TEXT DEFAULT '',
                    `group` TEXT DEFAULT ''
                )
            """)
            # 兼容旧库：为已存在的 skills 表补 group 列（业务分组）
            try:
                skill_cols = [r["name"] for r in conn.execute("PRAGMA table_info(skills)")]
                if "group" not in skill_cols:
                    conn.execute("ALTER TABLE skills ADD COLUMN `group` TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_tools (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    desc TEXT DEFAULT '',
                    icon TEXT DEFAULT '',
                    tag TEXT DEFAULT '',
                    danger INTEGER DEFAULT 0,
                    category TEXT DEFAULT '',
                    server_id TEXT DEFAULT '',
                    method TEXT DEFAULT 'POST',
                    path TEXT DEFAULT '',
                    params_schema TEXT DEFAULT '[]',
                    `group` TEXT DEFAULT ''
                )
            """)
            # 兼容旧库：为已存在的 mcp_tools 表补 server_id / method / path / params_schema / group 列
            try:
                tool_cols = [r["name"] for r in conn.execute("PRAGMA table_info(mcp_tools)")]
                if "server_id" not in tool_cols:
                    conn.execute("ALTER TABLE mcp_tools ADD COLUMN server_id TEXT DEFAULT ''")
                if "method" not in tool_cols:
                    conn.execute("ALTER TABLE mcp_tools ADD COLUMN method TEXT DEFAULT 'POST'")
                if "path" not in tool_cols:
                    conn.execute("ALTER TABLE mcp_tools ADD COLUMN path TEXT DEFAULT ''")
                if "params_schema" not in tool_cols:
                    conn.execute("ALTER TABLE mcp_tools ADD COLUMN params_schema TEXT DEFAULT '[]'")
                if "group" not in tool_cols:
                    conn.execute("ALTER TABLE mcp_tools ADD COLUMN `group` TEXT DEFAULT ''")
            except Exception:
                pass
            # MCP Server 表：9010 MCP 工具网关 + 可配置的外部 MCP Server（MCP Hub 等）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    desc TEXT DEFAULT '',
                    base_url TEXT DEFAULT '',
                    type TEXT DEFAULT 'gateway',
                    auth TEXT DEFAULT '',
                    status TEXT DEFAULT 'online',
                    last_sync TEXT DEFAULT '',
                    `group` TEXT DEFAULT ''
                )
            """)
            # 兼容旧库：为已存在的 mcp_servers 表补 type/auth/status/last_sync/group 列
            try:
                srv_cols = [r["name"] for r in conn.execute("PRAGMA table_info(mcp_servers)")]
                if "type" not in srv_cols:
                    conn.execute("ALTER TABLE mcp_servers ADD COLUMN type TEXT DEFAULT 'gateway'")
                if "auth" not in srv_cols:
                    conn.execute("ALTER TABLE mcp_servers ADD COLUMN auth TEXT DEFAULT ''")
                if "status" not in srv_cols:
                    conn.execute("ALTER TABLE mcp_servers ADD COLUMN status TEXT DEFAULT 'online'")
                if "last_sync" not in srv_cols:
                    conn.execute("ALTER TABLE mcp_servers ADD COLUMN last_sync TEXT DEFAULT ''")
                if "group" not in srv_cols:
                    conn.execute("ALTER TABLE mcp_servers ADD COLUMN `group` TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employee_skills (
                    employee_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    PRIMARY KEY (employee_id, skill_id)
                )
            """)
            # 兼容旧库：补充 enabled 列（停用技能保留关联但不参与 MCP 工具推导）
            try:
                _es_cols = [c[1] for c in conn.execute("PRAGMA table_info(employee_skills)").fetchall()]
                if "enabled" not in _es_cols:
                    conn.execute("ALTER TABLE employee_skills ADD COLUMN enabled INTEGER DEFAULT 1")
            except Exception:
                pass
            # 知识库实体表（RAG 元数据；向量本体存 ChromaDB）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_bases (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    doc_count INTEGER DEFAULT 0,
                    chunk_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # 知识切块表（元数据 + 文本；向量本体存 ChromaDB）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    kb_id TEXT NOT NULL,
                    doc_name TEXT DEFAULT '',
                    chunk_index INTEGER DEFAULT 0,
                    content TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_kb ON knowledge_chunks(kb_id)")
            # 智能体 ↔ 知识库 多对多绑定表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employee_kb (
                    employee_id TEXT NOT NULL,
                    kb_id TEXT NOT NULL,
                    PRIMARY KEY (employee_id, kb_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_mcp (
                    skill_id TEXT NOT NULL,
                    mcp_id TEXT NOT NULL,
                    PRIMARY KEY (skill_id, mcp_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS long_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    employee_id TEXT DEFAULT '',
                    schedule TEXT DEFAULT '',
                    update_time TEXT DEFAULT '',
                    executions TEXT DEFAULT '[]'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id TEXT PRIMARY KEY,
                    type TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    level TEXT DEFAULT '',
                    time TEXT DEFAULT '',
                    source_id TEXT DEFAULT '',
                    auto_skill TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS todo_history (
                    id TEXT PRIMARY KEY,
                    type TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    level TEXT DEFAULT '',
                    time TEXT DEFAULT '',
                    handled_time TEXT DEFAULT '',
                    result TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bg_tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT '',
                    desc TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT DEFAULT ''
                )
            """)
            conn.commit()
        finally:
            conn.close()


def ensure_conversation(conv_id: str, title: str) -> None:
    """新建会话；若已存在则更新标题"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
                (conv_id, title, now, now),
            )
            conn.commit()
        finally:
            conn.close()


def save_user_message(conv_id: str, content: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                (conv_id, content, now),
            )
            conn.commit()
        finally:
            conn.close()


def save_agent_message(conv_id: str, thought: str, tools: list, conclusion: str, route: dict,
                       engine: str = None, dsh_session_id: str = None) -> None:
    """保存 agent 消息；engine / dsh_session_id 用于更新会话的引擎观测字段（P3）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, thought, tools, conclusion, route, created_at) "
                "VALUES (?, 'agent', ?, ?, ?, ?, ?)",
                (conv_id, thought, json.dumps(tools, ensure_ascii=False), conclusion,
                 json.dumps(route, ensure_ascii=False) if route else "", now),
            )
            if engine is not None or dsh_session_id is not None:
                sets = ["updated_at=?"]
                vals = [now]
                if engine is not None:
                    sets.append("engine=?")
                    vals.append(engine)
                if dsh_session_id is not None:
                    sets.append("dsh_session_id=?")
                    vals.append(dsh_session_id)
                vals.append(conv_id)
                conn.execute(f"UPDATE conversations SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
        finally:
            conn.close()


def list_conversations() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, project_id, pinned, share_id "
                "FROM conversations ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["pinned"] = bool(d.get("pinned", 0))
                result.append(d)
            return result
        finally:
            conn.close()


# ═══════════════════════════════════════════
# 项目 CRUD
# ═══════════════════════════════════════════

def db_create_project(name: str) -> str:
    """新建项目，返回项目 ID"""
    pid = "proj-" + uuid.uuid4().hex[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                (pid, name, now),
            )
            conn.commit()
        finally:
            conn.close()
    return pid


def db_list_projects() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT p.id, p.name, p.created_at, "
                "(SELECT COUNT(*) FROM conversations c WHERE c.project_id = p.id) AS conv_count "
                "FROM projects p ORDER BY p.created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def db_rename_project(project_id: str, name: str) -> bool:
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def db_delete_project(project_id: str) -> None:
    """删除项目，同时把其下会话移回「未分组」"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("UPDATE conversations SET project_id='' WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.commit()
        finally:
            conn.close()


# ═══════════════════════════════════════════
# 会话操作：置顶 / 重命名 / 移动 / 删除 / 分享
# ═══════════════════════════════════════════

def db_update_conversation(conv_id: str, fields: dict) -> bool:
    """按需更新会话字段（title / project_id / pinned），返回是否命中记录"""
    allowed = {"title", "project_id", "pinned"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return False
    params.append(conv_id)
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                f"UPDATE conversations SET {', '.join(sets)} WHERE id=?",
                params,
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def db_delete_conversation(conv_id: str) -> None:
    """删除会话及其全部消息"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
            conn.commit()
        finally:
            conn.close()


def db_get_deleted_mock_convs() -> list:
    """读取已删除的 mock 会话 id 列表（meta 标记，保证刷新后不再出现）"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='deleted_mock_convs'").fetchone()
            if row and row["value"]:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return []
            return []
        finally:
            conn.close()


def db_mark_mock_conv_deleted(conv_id: str) -> None:
    """记录会话删除标记（幂等）。

    真实会话删除时已删库记录；数字员工详情里的预置 mock 会话不在库中，
    靠该标记持久化「已删除」状态，避免刷新后重新出现。
    """
    if not conv_id:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            cur = []
            row = conn.execute("SELECT value FROM meta WHERE key='deleted_mock_convs'").fetchone()
            if row and row["value"]:
                try:
                    cur = json.loads(row["value"])
                except Exception:
                    cur = []
            if conv_id not in cur:
                cur.append(conv_id)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('deleted_mock_convs', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(cur, ensure_ascii=False),),
                )
                conn.commit()
        finally:
            conn.close()


def db_share_conversation(conv_id: str) -> str:
    """为会话生成/复用分享 ID（短随机串），返回 share_id"""
    share_id = "s" + uuid.uuid4().hex[:8]
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT share_id FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            if row and row["share_id"]:
                return row["share_id"]
            conn.execute("UPDATE conversations SET share_id=? WHERE id=?", (share_id, conv_id))
            conn.commit()
        finally:
            conn.close()
    return share_id


def db_get_conversation_share(conv_id: str) -> str:
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT share_id FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            return (row["share_id"] if row else "") or ""
        finally:
            conn.close()


def db_get_conv_by_share(share_id: str):
    """通过 share_id 定位会话，返回 (conv_id, title) 或 None"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id, title FROM conversations WHERE share_id=?", (share_id,)
            ).fetchone()
            return (row["id"], row["title"]) if row else None
        finally:
            conn.close()


def get_conversation_messages(conv_id: str) -> dict:
    with _db_lock:
        conn = _get_conn()
        try:
            conv = conn.execute("SELECT id, title FROM conversations WHERE id=?", (conv_id,)).fetchone()
            if not conv:
                return {"conversation_id": conv_id, "title": "新会话", "messages": []}
            rows = conn.execute(
                "SELECT role, content, thought, tools, conclusion, route FROM messages WHERE conversation_id=? ORDER BY id ASC",
                (conv_id,),
            ).fetchall()
            messages = []
            for r in rows:
                if r["role"] == "user":
                    messages.append({"role": "user", "content": r["content"]})
                else:
                    messages.append({
                        "role": "agent",
                        "thought": r["thought"],
                        "tools": json.loads(r["tools"] or "[]"),
                        "conclusion": r["conclusion"],
                        "route": json.loads(r["route"]) if r["route"] else None,
                    })
            return {"conversation_id": conv_id, "title": conv["title"], "messages": messages}
        finally:
            conn.close()


def _load_chat_history(conv_id: str, max_turns: int = 6) -> list:
    """读取会话历史，转为可喂给模型的 messages（只取 user 内容 + agent 结论），取最近 N 轮"""
    if not conv_id:
        return []
    data = get_conversation_messages(conv_id)
    history = []
    for m in data.get("messages", []):
        if m["role"] == "user":
            history.append({"role": "user", "content": m["content"]})
        else:
            conclusion = m.get("conclusion", "")
            if conclusion:
                history.append({"role": "assistant", "content": conclusion[:800]})
    # 每轮 = 1 user + 1 assistant，取最近 max_turns 轮
    return history[-(max_turns * 2):]


def seed_mock_conversations():
    """首次初始化时导入预置会话（meta 标记，仅导入一次）"""
    with _db_lock:
        conn = _get_conn()
        try:
            if conn.execute("SELECT value FROM meta WHERE key='conv_seeded'").fetchone():
                return
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for cid, cdata in MOCK_CONV_MESSAGES.items():
                conn.execute(
                    "INSERT OR REPLACE INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (cid, cdata.get("title", cid), now, now),
                )
                for m in cdata.get("messages", []):
                    if m["role"] == "user":
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                            (cid, m.get("content", ""), now),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, thought, tools, conclusion, route, created_at) "
                            "VALUES (?, 'agent', ?, ?, ?, '', ?)",
                            (cid, m.get("thought", ""), json.dumps(m.get("tools", []), ensure_ascii=False),
                             m.get("conclusion", ""), now),
                        )
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('conv_seeded', '1')")
            conn.commit()
        finally:
            conn.close()


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


# ═══════════════════════════════════════════
# 配置库 CRUD（员工/技能/MCP工具）
# ═══════════════════════════════════════════

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


def db_list_todos() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM todos ORDER BY id").fetchall()]
        finally:
            conn.close()


def db_list_todo_history() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM todo_history ORDER BY id").fetchall()]
        finally:
            conn.close()


def db_list_bg_tasks() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM bg_tasks ORDER BY id").fetchall()]
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════
#  AI 智能体一体化监控 API（参考 Langfuse：Traces / Observations / Sessions）
# ══════════════════════════════════════════════════════════════════════

# DeepSeek 成本估算单价（元 / 百万 tokens），可按实际定价修改
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


# ============ 知识库（RAG）数据层 ============

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


# ════════════════════════════════════════════════════════════
# 统一监控探针数据层
# ops_metrics 时序指标(保留1天) / ops_entities 本体实体
# ops_relations 本体关系 / incidents 自愈事件 / settings 配置
# ════════════════════════════════════════════════════════════

OPS_ENTITY_TYPES = ("server", "database", "network", "container", "middleware", "application")


def init_ops_db():
    """初始化运维监控表结构（统一探针采集的数据落库）"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_name TEXT NOT NULL DEFAULT '',
                    metric TEXT NOT NULL DEFAULT '',
                    value REAL NOT NULL DEFAULT 0,
                    unit TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_metrics_ts ON ops_metrics(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_metrics_ent ON ops_metrics(entity_type, entity_name, metric)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    metrics TEXT NOT NULL DEFAULT '{}',
                    attrs TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_entities_type ON ops_entities(type)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_relations (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    type TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (source, target, type)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    alert_id INTEGER NOT NULL DEFAULT 0,
                    rule_name TEXT NOT NULL DEFAULT '',
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_name TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'warning',
                    state TEXT NOT NULL DEFAULT 'detected',
                    message TEXT NOT NULL DEFAULT '',
                    fix_action TEXT NOT NULL DEFAULT '',
                    fix_log TEXT NOT NULL DEFAULT '',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    resolved_at TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_state ON incidents(state)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_logs_ts ON ops_logs(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_logs_src ON ops_logs(source, level)")

            # 远程探针隔离列：scope 标识数据来源主机（空=监控中心本机，非空=远程探针主机名）
            for _tbl in ("ops_entities", "ops_relations"):
                _cols = {r[1] for r in conn.execute(f"PRAGMA table_info({_tbl})")}
                if "scope" not in _cols:
                    conn.execute(f"ALTER TABLE {_tbl} ADD COLUMN scope TEXT NOT NULL DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_entities_scope ON ops_entities(scope)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_relations_scope ON ops_relations(scope)")
            conn.commit()
        finally:
            conn.close()


# ---- settings 配置 ----

def db_get_setting(key: str, default: str = "") -> str:
    row = _query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def db_set_setting(key: str, value: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value))
            conn.commit()
        finally:
            conn.close()


def db_get_settings_all() -> dict:
    rows = _query_rows("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


# ---- ops_metrics 时序指标 ----

def ops_save_metric(ts: str, entity_type: str, entity_name: str,
                    metric: str, value: float, unit: str = ""):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO ops_metrics (ts, entity_type, entity_name, metric, value, unit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, entity_type, entity_name, metric, float(value), unit))
            conn.commit()
        finally:
            conn.close()


def ops_save_metrics(ts: str, items):
    """批量写时序指标。items: list[(entity_type, entity_name, metric, value, unit)]"""
    if not items:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executemany(
                "INSERT INTO ops_metrics (ts, entity_type, entity_name, metric, value, unit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(ts, it[0], it[1], it[2], float(it[3]), it[4]) for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_metrics(entity_type: str = "", entity_name: str = "",
                    metric: str = "", minutes: int = 10) -> list:
    """按实体/指标/时间窗查询时序数据，按时间正序"""
    where, args = ["ts >= datetime('now', ?)"], ["-" + str(minutes) + " minutes"]
    if entity_type:
        where.append("entity_type = ?")
        args.append(entity_type)
    if entity_name:
        where.append("entity_name = ?")
        args.append(entity_name)
    if metric:
        where.append("metric = ?")
        args.append(metric)
    rows = _query_rows(
        "SELECT ts, entity_type, entity_name, metric, value, unit FROM ops_metrics "
        "WHERE " + " AND ".join(where) + " ORDER BY ts ASC", tuple(args))
    return [dict(r) for r in rows]


def ops_get_latest_value(entity_type: str, entity_name: str, metric: str,
                         default: float = 0.0) -> float:
    row = _query_one(
        "SELECT value FROM ops_metrics WHERE entity_type = ? AND entity_name = ? AND metric = ? "
        "ORDER BY ts DESC LIMIT 1",
        (entity_type, entity_name, metric))
    return row["value"] if row else default


def ops_get_latest_snapshot() -> dict:
    """最新一轮采集快照：{entity_name: {metric: value}}，用于告警检测"""
    rows = _query_rows(
        "SELECT entity_type, entity_name, metric, value FROM ops_metrics m "
        "WHERE ts = (SELECT MAX(ts) FROM ops_metrics)")
    snap: dict = {}
    for r in rows:
        snap.setdefault((r["entity_type"], r["entity_name"]), {})[r["metric"]] = r["value"]
    return snap


def ops_cleanup_old_metrics(retention_days: int = 1) -> int:
    """清理超过保留期的时序指标，返回删除行数"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM ops_metrics WHERE ts < datetime('now', ?)",
                ("-" + str(retention_days) + " days",))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


# ---- ops_logs 统一日志（探针日志采集器写入）----

def ops_save_logs(items):
    """批量写日志条目。items: list[(ts, source, level, message)]"""
    if not items:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executemany(
                "INSERT INTO ops_logs (ts, source, level, message) VALUES (?, ?, ?, ?)",
                [(it[0], it[1], it[2], it[3]) for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_logs(source: str = "", level: str = "", minutes: int = 30,
                 limit: int = 500) -> list:
    """按来源/级别/时间窗倒序查询日志"""
    where, args = ["ts >= datetime('now', ?)"], ["-" + str(minutes) + " minutes"]
    if source:
        where.append("source = ?")
        args.append(source)
    if level:
        where.append("level = ?")
        args.append(level)
    rows = _query_rows(
        "SELECT ts, source, level, message FROM ops_logs "
        "WHERE " + " AND ".join(where) + " ORDER BY ts DESC, id DESC LIMIT ?",
        tuple(args + [int(limit)]))
    return [dict(r) for r in rows]


def ops_count_logs(minutes: int = 10, level: str = "", source_prefix: str = "") -> int:
    """统计最近窗口内指定级别（默认全部）日志条数，用于告警检测。

    source_prefix 仅统计匹配前缀的来源（如 "app:" 只看应用日志，
    排除系统 syslog 噪音，避免 "应用日志错误突增" 规则被系统错误误触发）。
    """
    where, args = ["ts >= datetime('now', ?)"], ["-" + str(minutes) + " minutes"]
    if level:
        where.append("level = ?")
        args.append(level)
    if source_prefix:
        where.append("source LIKE ?")
        args.append(source_prefix + "%")
    row = _query_one(
        "SELECT COUNT(*) AS n FROM ops_logs WHERE " + " AND ".join(where),
        tuple(args))
    return int(row["n"]) if row else 0


def ops_cleanup_old_logs(retention_days: int = 1) -> int:
    """清理超过保留期的日志，返回删除行数"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM ops_logs WHERE ts < datetime('now', ?)",
                ("-" + str(retention_days) + " days",))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


# ---- ops_entities 本体实体 ----

def ops_upsert_entity(entity_id: str, etype: str, name: str, status: str,
                      metrics: dict, attrs: dict, ts: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO ops_entities (id, type, name, status, metrics, attrs, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "status = excluded.status, metrics = excluded.metrics, "
                "attrs = excluded.attrs, updated_at = excluded.updated_at",
                (entity_id, etype, name, status,
                 json.dumps(metrics, ensure_ascii=False),
                 json.dumps(attrs, ensure_ascii=False), ts))
            conn.commit()
        finally:
            conn.close()


def ops_save_entities(ts: str, items, scope: str = ""):
    """全量重建实体；按来源（scope）隔离：scope 为空重建本机（scope=''），非空重建对应远程探针"""
    with _db_lock:
        conn = _get_conn()
        try:
            if scope:
                conn.execute("DELETE FROM ops_entities WHERE scope = ?", (scope,))
            else:
                conn.execute("DELETE FROM ops_entities WHERE scope = ''")
            if items:
                conn.executemany(
                    "INSERT INTO ops_entities (id, type, name, status, metrics, attrs, updated_at, scope) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [(it["id"], it["type"], it["name"], it.get("status", "unknown"),
                      json.dumps(it.get("metrics", {}), ensure_ascii=False),
                      json.dumps(it.get("attrs", {}), ensure_ascii=False), ts, scope)
                     for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_entities(etype: str = "") -> list:
    if etype:
        rows = _query_rows(
            "SELECT * FROM ops_entities WHERE type = ? ORDER BY name", (etype,))
    else:
        rows = _query_rows("SELECT * FROM ops_entities ORDER BY type, name")
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["metrics"] = json.loads(d.get("metrics") or "{}")
        except Exception:
            d["metrics"] = {}
        try:
            d["attrs"] = json.loads(d.get("attrs") or "{}")
        except Exception:
            d["attrs"] = {}
        out.append(d)
    return out


def ops_get_entity(entity_id: str) -> dict:
    for e in ops_get_entities():
        if e["id"] == entity_id:
            return e
    return {}


# ---- ops_relations 本体关系 ----

def ops_save_relations(ts: str, items, scope: str = ""):
    """全量重建关系；按来源（scope）隔离：scope 为空重建本机（scope=''），非空重建对应远程探针"""
    with _db_lock:
        conn = _get_conn()
        try:
            if scope:
                conn.execute("DELETE FROM ops_relations WHERE scope = ?", (scope,))
            else:
                conn.execute("DELETE FROM ops_relations WHERE scope = ''")
            if items:
                conn.executemany(
                    "INSERT INTO ops_relations (source, target, type, updated_at, scope) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [(it[0], it[1], it[2], ts, scope) for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_relations() -> list:
    rows = _query_rows("SELECT source, target, type FROM ops_relations")
    return [dict(r) for r in rows]


# ---- incidents 自愈事件 ----

def incident_create(incident_id: str, alert_id: int, rule_name: str,
                    entity_type: str, entity_name: str, severity: str,
                    message: str, ts: str) -> dict:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO incidents (id, alert_id, rule_name, entity_type, entity_name, "
                "severity, state, message, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'detected', ?, ?, ?)",
                (incident_id, alert_id, rule_name, entity_type, entity_name,
                 severity, message, ts, ts))
            conn.commit()
        finally:
            conn.close()
    return incident_get(incident_id)


def incident_update(incident_id: str, **fields):
    allowed = ("state", "message", "fix_action", "fix_log", "retry_count",
               "updated_at", "resolved_at")
    sets, args = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            args.append(v)
    if not sets:
        return
    args.append(incident_id)
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE incidents SET " + ", ".join(sets) + " WHERE id = ?", tuple(args))
            conn.commit()
        finally:
            conn.close()


def incident_get(incident_id: str) -> dict:
    row = _query_one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    return dict(row) if row else {}


def incident_list(state: str = "", limit: int = 100) -> list:
    if state:
        rows = _query_rows(
            "SELECT * FROM incidents WHERE state = ? ORDER BY created_at DESC LIMIT ?",
            (state, limit))
    else:
        rows = _query_rows(
            "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]
