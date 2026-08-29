# -*- coding: utf-8 -*-
"""建表：会话库 / 配置库初始化（init_*）"""

from .base import (
    _db_lock,
    _ensure_column,
    _get_conn,
)

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
            # 告警中心增强（v2）：类型 / 实体 / 处置建议 / 关联影响 / 确认状态（幂等补列，兼容存量库）
            for _col, _ddl in (
                ("type", "TEXT DEFAULT ''"),
                ("entity_type", "TEXT DEFAULT ''"),
                ("entity_name", "TEXT DEFAULT ''"),
                ("suggestion", "TEXT DEFAULT ''"),
                ("impact", "TEXT DEFAULT ''"),
                ("acked", "INTEGER DEFAULT 0"),
                ("acked_at", "TEXT DEFAULT ''"),
                ("ack_by", "TEXT DEFAULT ''"),
            ):
                _ensure_column(conn, "alerts", _col, _ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_type ON alerts(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_entity ON alerts(entity_type, entity_name)")
            _ensure_column(conn, "alert_rules", "type", "TEXT DEFAULT ''")
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
                    workbench_json TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1
                )
            """)
            _ensure_column(conn, "employees", "enabled", "INTEGER DEFAULT 1")
            _ensure_column(conn, "employees", "workbench_json", "TEXT DEFAULT ''")
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


def init_spare_mail_db():
    """初始化「备件邮件询价」数字员工数据表。

    - spare_mail_task：动态运行态任务单表。
    - spare_mail_config：静态配置（邮件/飞书凭据、审批人、供应商、邮件模板），
      由配置管理页面维护，优先于 skill JSON 与 .env。
    """
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
    CREATE TABLE IF NOT EXISTS spare_mail_task (
        task_id TEXT PRIMARY KEY,
        thread_msg_id TEXT DEFAULT '',
        d_mail_msg_id TEXT DEFAULT '',
        inquiry_body TEXT DEFAULT '',
        from_email TEXT DEFAULT '',
        inquiry_to_json TEXT DEFAULT '[]',
        inquiry_cc_json TEXT DEFAULT '[]',
        approver_email TEXT DEFAULT '',
        project_no TEXT DEFAULT '',
        project_name TEXT DEFAULT '',
        part_type TEXT DEFAULT '',
        brand TEXT DEFAULT '',
        pn TEXT DEFAULT '',
        spec TEXT DEFAULT '',
        `condition` TEXT DEFAULT '',
        `count` TEXT DEFAULT '',
        address TEXT DEFAULT '',
        urgent TEXT DEFAULT '',
        latest_ship_time TEXT DEFAULT '',
        inquiry_deadline TEXT DEFAULT '',
        suppliers_json TEXT DEFAULT '[]',
        quotes_json TEXT DEFAULT '[]',
        lowest_supplier TEXT DEFAULT '',
        lowest_quote TEXT DEFAULT '',
        approval_state TEXT DEFAULT '',
        approval_result TEXT DEFAULT '',
        target_supplier TEXT DEFAULT '',
        -- 双流水：内部审批流 / 外部报价流
        internal_status TEXT DEFAULT '',
        external_status TEXT DEFAULT '',
        shipped_no TEXT DEFAULT '',
        shipped_mail_meta TEXT DEFAULT '{}',
        e_mail_msg_id TEXT DEFAULT '',
        e_refs_chain TEXT DEFAULT '',
        status TEXT DEFAULT '',
        latest_step TEXT DEFAULT '',
        created_at TEXT DEFAULT '',
        updated_at TEXT DEFAULT ''
    )
""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spare_mail_task_status ON spare_mail_task(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spare_mail_task_thread ON spare_mail_task(thread_msg_id)")
            # 旧表迁移：补齐双流/紧急程度等新增列（CREATE IF NOT EXISTS 对已存在表不生效）
            _add_cols = {
                "urgent": "TEXT DEFAULT ''",
                "latest_ship_time": "TEXT DEFAULT ''",
                "internal_status": "TEXT DEFAULT ''",
                "external_status": "TEXT DEFAULT ''",
                "shipped_no": "TEXT DEFAULT ''",
                "inquiry_body": "TEXT DEFAULT ''",
                "e_mail_msg_id": "TEXT DEFAULT ''", "e_refs_chain": "TEXT DEFAULT ''",
                "from_email": "TEXT DEFAULT ''",
                "inquiry_to_json": "TEXT DEFAULT '[]'", "inquiry_cc_json": "TEXT DEFAULT '[]'",
                "shipped_mail_meta": "TEXT DEFAULT '{}'",
            }
            existing = {r[1] for r in conn.execute("PRAGMA table_info(spare_mail_task)").fetchall()}
            for c, ddl in _add_cols.items():
                if c not in existing:
                    try:
                        conn.execute(f"ALTER TABLE spare_mail_task ADD COLUMN {c} {ddl}")
                    except Exception:
                        pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spare_mail_config (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT ''
                )
            """)
            conn.commit()
        finally:
            conn.close()
