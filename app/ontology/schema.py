# -*- coding: utf-8 -*-
"""本体轨数据库 schema（NO-012 emp-009）
独立于现轨 `spare_mail_task` / `spare_mail_config`，落 `neuops_ontology.db`。
"""
import os
import sqlite3
import threading

from ..config import BASE_DIR

ONT_DB_PATH = os.getenv("ONT_DB_PATH", os.path.join(BASE_DIR, "neuops_ontology.db"))
_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(ONT_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_DDL = [
    # 预会话：立项前临时实体（多轮补齐）
    """CREATE TABLE IF NOT EXISTS o_session (
        session_id TEXT PRIMARY KEY,
        initiator_person_id TEXT,
        thread_id TEXT,
        status TEXT DEFAULT 'PRE_CHECK',
        create_time TEXT,
        update_time TEXT,
        abandon_reason TEXT,
        auto_abandon_threshold_hours INTEGER DEFAULT 24
    )""",
    # 任务：业务根实体（独立于 spare_mail_task）
    """CREATE TABLE IF NOT EXISTS o_task (
        task_id TEXT PRIMARY KEY,
        session_id TEXT,
        threat_msg_id TEXT DEFAULT '',
        from_email TEXT DEFAULT '',
        spare_info TEXT DEFAULT '{}',
        urgency_raw TEXT DEFAULT '',
        quote_deadline TEXT DEFAULT '',
        target_supplier_list TEXT DEFAULT '[]',
        target_supplier TEXT DEFAULT '',
        tracking_number TEXT DEFAULT '',
        close_feedback TEXT DEFAULT '',
        status TEXT DEFAULT 'INIT',
        mode TEXT DEFAULT 'ontology',
        create_time TEXT,
        close_time TEXT,
        update_time TEXT
    )""",
    # 人员：映射业务主数据
    """CREATE TABLE IF NOT EXISTS o_person (
        person_id TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        email TEXT DEFAULT '',
        role TEXT DEFAULT ''
    )""",
    # 邮件：emailMessageId 幂等唯一键
    """CREATE TABLE IF NOT EXISTS o_email (
        email_message_id TEXT PRIMARY KEY,
        task_id TEXT DEFAULT '',
        session_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        send_time TEXT DEFAULT '',
        template_type TEXT DEFAULT '',
        from_email TEXT DEFAULT '',
        to_json TEXT DEFAULT '[]',
        cc_json TEXT DEFAULT '[]',
        in_reply_to TEXT DEFAULT '',
        `references` TEXT DEFAULT ''
    )""",
    # 报价：独立生命周期
    """CREATE TABLE IF NOT EXISTS o_supplier_quote (
        quote_id TEXT PRIMARY KEY,
        task_id TEXT DEFAULT '',
        supplier_person_id TEXT DEFAULT '',
        quote_raw_text TEXT DEFAULT '',
        unit_price TEXT DEFAULT '',
        receive_time TEXT DEFAULT '',
        is_timeout INTEGER DEFAULT 0,
        is_valid INTEGER DEFAULT 1,
        invalid_reason TEXT DEFAULT ''
    )""",
    # 审计：仅追加，禁止修改/删除
    """CREATE TABLE IF NOT EXISTS o_audit_log (
        audit_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        biz_type TEXT,
        biz_id TEXT,
        action TEXT,
        operator TEXT,
        operate_time TEXT,
        content_snapshot TEXT DEFAULT '{}',
        remark TEXT DEFAULT ''
    )""",
    # 阶段A只读对照：本体轨推断动作 vs 现轨实际
    """CREATE TABLE IF NOT EXISTS o_alignment (
        alignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        legacy_external TEXT,
        legacy_internal TEXT,
        proposed_action TEXT,
        proposed_external TEXT,
        proposed_internal TEXT,
        aligned INTEGER,
        diff TEXT DEFAULT '',
        create_time TEXT
    )""",
]


def init():
    with _lock:
        conn = get_conn()
        try:
            for ddl in _DDL:
                conn.execute(ddl)
            conn.commit()
        finally:
            conn.close()


def ensure_core_tables():
    init()