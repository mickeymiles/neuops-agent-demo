# -*- coding: utf-8 -*-
"""业务化落库后端：把智能体执行链路的状态写进 9006 业务主表。

架构背景
--------
原先 emp-009 是「本体轨」，任务落 `contract_ontology.db` 的 o_task（ABox），
本体承担备件采购的执行建模。现本体退出本环节（转向更宏观的统筹建设），
备件采购回归普通业务逻辑：读邮箱 → 建任务 → 状态机流转，任务直接写
9006 的 **业务主表 `procurement_task`**。

本模块与 `store.py`（本体 ABox 落库）**接口兼容**，由 `ONT_STORE_BACKEND` 切换：
  - `biz`（默认，新链路）→ 本模块，写 9006 业务表
  - `ontology`（旧链路）→ store.py，写 contract_ontology.db

落点映射
--------
  任务        → procurement_task（业务字段逐列映射 + spare_info 整体存一份供回读）
  邮件去重    → procurement_mail_seen（email_message_id 唯一键，取代 o_email）
  扫描水位    → procurement_agent_state（kv）
  审计        → procurement_op_log
  对齐/人员   → 本体专属，业务化后降级为 no-op（保留接口以免调用方报错）

并发：连接时设 `PRAGMA journal_mode=WAL`，与 9006 页面只读查询共存。
"""
import json
import os
import sqlite3
import threading
import time

_lock = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def db_path():
    """9006 业务库路径（与 proc_9006_config 同源）。"""
    try:
        from app.db import proc_9006_config as p9
        return p9.db_path()
    except Exception:
        return os.getenv("PROC_9006_DB_PATH", "")


# 本模块写入 procurement_task 的列（表不存在时按此建表，已存在则幂等补列）
_TASK_COLS = (
    "task_id", "spare_part_model", "purchase_qty", "emergency_level", "reply_deadline",
    "inquiry_deadline", "inquiry_supplier_list", "suppliers_json", "replied_supplier_quotes",
    "quotes_json", "selected_supplier", "target_supplier", "lowest_supplier", "lowest_quote",
    "logistics_no", "deal_unit_price", "task_status", "creator", "create_time", "updated_at",
    "project_no", "project_name", "part_type", "brand", "pn", "spec", "condition", "count",
    "address", "urgent", "approval_state", "approver_email", "internal_status", "external_status",
    "from_email", "source", "latest_ship_time", "spare_info", "session_id", "threat_msg_id",
    "close_feedback", "mode", "close_time", "status",
)
# NOT NULL 列需要非空默认值，否则精简建表后插入会失败
_NOT_NULL_COLS = {"spare_part_model": "TEXT NOT NULL DEFAULT ''",
                  "purchase_qty": "REAL NOT NULL DEFAULT 0",
                  "emergency_level": "TEXT NOT NULL DEFAULT '48h'"}

_schema_ready = False


def _ensure_schema(conn):
    """幂等建表/补列。

    生产环境表由 9006 的 init_procurement_db() 创建（54 列），此处只补列；
    测试环境连临时库时表不存在，则按 _TASK_COLS 建一张精简表。
    """
    conn.execute("CREATE TABLE IF NOT EXISTS procurement_task (task_id TEXT PRIMARY KEY)")
    existing = {r[1] for r in conn.execute("PRAGMA table_info(procurement_task)")}
    for col in _TASK_COLS:
        if col not in existing:
            col_ddl = _NOT_NULL_COLS.get(col, "TEXT DEFAULT ''")
            conn.execute(f"ALTER TABLE procurement_task ADD COLUMN {col} {col_ddl}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS procurement_mail_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_message_id TEXT NOT NULL,
            task_id TEXT DEFAULT '',
            direction TEXT DEFAULT 'in',
            subject TEXT DEFAULT '',
            body TEXT DEFAULT '',
            from_email TEXT DEFAULT '',
            to_json TEXT DEFAULT '[]',
            cc_json TEXT DEFAULT '[]',
            in_reply_to TEXT DEFAULT '',
            `references` TEXT DEFAULT '',
            claim_status TEXT DEFAULT 'claimed',
            claim_error TEXT DEFAULT '',
            received_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_proc_mail_seen_mid "
                 "ON procurement_mail_seen(email_message_id)")
    # 幂等补列（表早于本版本创建时）。
    # 注意：`references` 是 SQLite 保留字，补列必须加反引号；
    # 且单列失败不应中断整轮建表，否则后续表建不出来（曾因此吞掉认领异常）。
    _ms_existing = {r[1] for r in conn.execute("PRAGMA table_info(procurement_mail_seen)")}
    for _name, _ddl in (("body", "body"), ("to_json", "to_json"), ("cc_json", "cc_json"),
                        ("in_reply_to", "in_reply_to"), ("references", "`references`")):
        if _name not in _ms_existing:
            try:
                conn.execute(f"ALTER TABLE procurement_mail_seen ADD COLUMN {_ddl} TEXT DEFAULT ''")
            except Exception:
                pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS procurement_agent_state (
            state_key TEXT PRIMARY KEY,
            state_value TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS procurement_op_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            operator TEXT DEFAULT '',
            action TEXT NOT NULL,
            action_time TEXT DEFAULT '',
            remark TEXT DEFAULT ''
        )
    """)
    conn.commit()


def _connect():
    global _schema_ready
    p = db_path()
    if not p or not os.path.exists(p):
        raise RuntimeError("9006 业务库不可达: %s" % p)
    conn = sqlite3.connect(p, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
    except Exception:
        pass
    if not _schema_ready:
        try:
            _ensure_schema(conn)
            _schema_ready = True
        except Exception:
            pass
    return conn


# ── 状态映射：本体双流状态 → 业务表中文 task_status ──────────────────
_STATUS_RULES = [
    (lambda i, e: i in ("CLOSED_ABORT",) or e == "CLOSED_ABORT", "任务已取消"),
    (lambda i, e: i in ("R_SETTLE", "R_CLOSED", "CLOSED_MANUAL") or e in ("DONE",), "流程闭环"),
    (lambda i, e: i in ("R_WAIT_SHIPPING", "R_WAIT_ENGINEER_CLOSE") or e == "SHIPPED", "供应商发货中"),
    (lambda i, e: i in ("R_SEND",) or e == "ORDER_CONFIRM", "已选型确认"),
]


def _task_status(internal="", external=""):
    i, e = (internal or ""), (external or "")
    for pred, label in _STATUS_RULES:
        try:
            if pred(i, e):
                return label
        except Exception:
            continue
    return "询比价进行中"


def _fnum(v, default=0.0):
    try:
        return float(str(v).strip() or default)
    except Exception:
        return default


def _task_to_row(task: dict):
    """本体任务 dict → procurement_task 一行（业务字段映射）。"""
    si = task.get("spare_info") or {}
    if isinstance(si, str):
        try:
            si = json.loads(si)
        except Exception:
            si = {}
    suppliers = si.get("suppliers") or []
    quotes = si.get("quotes") or []
    # 最低价：优先取报价里最小的 unit_price
    low_email, low_price = "", ""
    try:
        cand = [q for q in quotes if str(q.get("unit_price") or "").strip()]
        if cand:
            lo = min(cand, key=lambda q: _fnum(q.get("unit_price"), 10 ** 12))
            low_email = str(lo.get("email") or "")
            low_price = str(lo.get("unit_price") or "")
    except Exception:
        pass
    approvers = si.get("approver_emails") or []
    cnt = str(si.get("count") or "")
    part_model = " ".join(
        x for x in (str(si.get("brand") or ""), str(si.get("pn") or "")) if x
    ).strip() or str(si.get("part_type") or "")
    urgent = str(si.get("urgent") or task.get("urgency_raw") or "48h")
    return {
        "task_id": task.get("task_id") or "",
        "spare_part_model": part_model,
        "purchase_qty": _fnum(cnt, 0.0),
        "emergency_level": urgent,
        "reply_deadline": str(si.get("quote_deadline") or task.get("quote_deadline") or ""),
        "inquiry_deadline": str(si.get("quote_deadline") or task.get("quote_deadline") or ""),
        "inquiry_supplier_list": json.dumps(suppliers, ensure_ascii=False),
        "suppliers_json": json.dumps(suppliers, ensure_ascii=False),
        "replied_supplier_quotes": json.dumps(quotes, ensure_ascii=False),
        "quotes_json": json.dumps(quotes, ensure_ascii=False),
        "selected_supplier": str(si.get("target_supplier") or task.get("target_supplier") or ""),
        "target_supplier": str(si.get("target_supplier") or task.get("target_supplier") or ""),
        "lowest_supplier": low_email,
        "lowest_quote": low_price,
        "logistics_no": str(task.get("tracking_number") or si.get("tracking_no") or ""),
        "deal_unit_price": _fnum(low_price, 0.0) if low_price else 0.0,
        "task_status": _task_status(task.get("internal_status"), task.get("external_status")),
        "creator": str(task.get("from_email") or ""),
        "create_time": task.get("create_time") or _now(),
        "updated_at": task.get("update_time") or _now(),
        "project_no": str(si.get("project_no") or ""),
        "project_name": str(si.get("project_name") or ""),
        "part_type": str(si.get("part_type") or ""),
        "brand": str(si.get("brand") or ""),
        "pn": str(si.get("pn") or ""),
        "spec": str(si.get("spec") or ""),
        "condition": str(si.get("condition") or ""),
        "count": cnt,
        "address": str(si.get("address") or ""),
        "urgent": urgent,
        "approval_state": ("已驳回" if si.get("approval_rejected")
                           else ("已通过" if si.get("approval_choice") else "待审批")),
        "approver_email": (approvers[0] if isinstance(approvers, list) and approvers else str(approvers or "")),
        "internal_status": str(task.get("internal_status") or ""),
        "external_status": str(task.get("external_status") or ""),
        "from_email": str(task.get("from_email") or ""),
        "source": "邮件",
        "latest_ship_time": str(si.get("latest_ship_time") or ""),
        "spare_info": json.dumps(si, ensure_ascii=False),
        "session_id": str(task.get("session_id") or ""),
        "threat_msg_id": str(task.get("threat_msg_id") or si.get("inquiry_mid") or ""),
        "close_feedback": str(task.get("close_feedback") or ""),
        "mode": str(task.get("mode") or "ontology"),
        "close_time": str(task.get("close_time") or ""),
        "status": str(task.get("status") or "INIT"),
    }


def _row_to_task(r):
    """procurement_task 一行 → 本体任务 dict（还原 spare_info 供流程继续）。"""
    t = dict(r)
    try:
        si = json.loads(t.get("spare_info") or "{}")
    except Exception:
        si = {}
    # 用列上的权威值回填，避免 spare_info 快照过期
    for k_src, k_si in (("target_supplier", "target_supplier"),
                        ("logistics_no", "tracking_no"),
                        ("internal_status", None),
                        ("external_status", None)):
        v = t.get(k_src)
        if v and k_si:
            si[k_si] = v
    t["spare_info"] = si
    t["urgency_raw"] = t.get("urgent") or t.get("emergency_level") or ""
    t["quote_deadline"] = t.get("inquiry_deadline") or t.get("reply_deadline") or ""
    t["tracking_number"] = t.get("logistics_no") or ""
    try:
        t["target_supplier_list"] = json.loads(t.get("suppliers_json") or "[]")
    except Exception:
        t["target_supplier_list"] = []
    return t


# ────────────────────────── 任务 ──────────────────────────
def upsert_task(task: dict):
    if not task.get("task_id"):
        return
    row = _task_to_row(task)
    cols = list(row.keys())
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "task_id")
    sql = (f"INSERT INTO procurement_task ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT(task_id) DO UPDATE SET {updates}")
    with _lock:
        conn = _connect()
        try:
            conn.execute(sql, [row[c] for c in cols])
            conn.commit()
        finally:
            conn.close()


def get_task(task_id: str):
    with _lock:
        conn = _connect()
        try:
            r = conn.execute("SELECT * FROM procurement_task WHERE task_id=?", (task_id,)).fetchone()
            return _row_to_task(r) if r else None
        finally:
            conn.close()


def list_tasks(limit=500):
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM procurement_task WHERE source='邮件' AND task_id LIKE 'OT-%' "
                "ORDER BY create_time DESC LIMIT ?", (limit,)).fetchall()
            return [_row_to_task(r) for r in rows]
        finally:
            conn.close()


# ────────────────────────── 邮件去重 ──────────────────────────
def _mid(m):
    return (m.get("email_message_id") or m.get("message_id") or "").strip()


_SEEN_MAIL_COLS = ("email_message_id", "task_id", "direction", "subject", "body",
                   "from_email", "to_json", "cc_json", "in_reply_to", "references")


def _mail_row(m: dict):
    """mail dict → procurement_mail_seen 一行（登记时保留正文，供窗口滑过后重试）。"""
    return (
        (m.get("email_message_id") or m.get("message_id") or "").strip(),
        m.get("task_id", ""), m.get("direction", "in"),
        m.get("title", "") or m.get("subject", ""),
        m.get("body", "") or m.get("mail_body_text", ""),
        m.get("from_email", ""),
        json.dumps(m.get("to_email_list") or [], ensure_ascii=False),
        json.dumps(m.get("cc_email_list") or [], ensure_ascii=False),
        m.get("in_reply_to", ""), m.get("references", ""),
    )


def upsert_email(m: dict):
    """见过即消费：存在则跳过，不存在则登记并返回 True。"""
    mid = _mid(m)
    if not mid:
        return False
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("SELECT 1 FROM procurement_mail_seen WHERE email_message_id=?", (mid,))
            if cur.fetchone():
                return False
            conn.execute(
                "INSERT INTO procurement_mail_seen (email_message_id, task_id, direction, subject,"
                " body, from_email, to_json, cc_json, in_reply_to, `references`, claim_status,"
                " received_at) VALUES (?,?,?,?,?,?,?,?,?,?,'done',?)",
                _mail_row(m) + (_now(),))
            conn.commit()
            return True
        finally:
            conn.close()


def try_claim_email(m: dict):
    """两阶段认领：返回 True 表示需要处理（新邮件或上次未完成）。

    与 store.py 语义一致：处理成功后须回调 mark_email_claimed 置 done。
    """
    mid = _mid(m)
    if not mid:
        return False
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT claim_status FROM procurement_mail_seen WHERE email_message_id=?", (mid,)).fetchone()
            if row is not None:
                return (row["claim_status"] or "") != "done"
            conn.execute(
                "INSERT INTO procurement_mail_seen (email_message_id, task_id, direction, subject,"
                " body, from_email, to_json, cc_json, in_reply_to, `references`, claim_status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,'pending')",
                _mail_row(m))
            conn.commit()
            return True
        finally:
            conn.close()


def mark_email_claimed(mid: str, task_id: str = ""):
    if not mid:
        return
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE procurement_mail_seen SET claim_status='done', task_id=COALESCE(NULLIF(?,''),task_id),"
                " claim_error='', updated_at=? WHERE email_message_id=?",
                (task_id or "", _now(), mid))
            conn.commit()
        finally:
            conn.close()


def mark_email_failed(mid: str, err: str = ""):
    if not mid:
        return
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE procurement_mail_seen SET claim_status='failed', claim_error=?, updated_at=?"
                " WHERE email_message_id=?", (str(err)[:400], _now(), mid))
            conn.commit()
        finally:
            conn.close()


def list_unclaimed_emails(limit=100):
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM procurement_mail_seen WHERE claim_status<>'done' ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def pending_claim_mails(limit=100):
    """把未闭环（pending/failed）的邮件还原成 mail 形状，供认领重试。

    与本体后端 store.pending_claim_mails 语义一致：重试不依赖 IMAP 扫描窗口，
    正文已在登记时落库，窗口滑过也能救回，不会丢单。
    """
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM procurement_mail_seen WHERE IFNULL(claim_status,'') IN ('pending','failed')"
                " ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
        finally:
            conn.close()
    out = []
    for r in rows:
        d = dict(r)

        def _j(v, dflt="[]"):
            try:
                return json.loads(v or dflt)
            except Exception:
                return json.loads(dflt)

        out.append({
            "message_id": d.get("email_message_id") or "",
            "subject": d.get("subject") or "",
            "mail_body_text": d.get("body") or "",
            "from_email": d.get("from_email") or "",
            "in_reply_to": d.get("in_reply_to") or "",
            "references": d.get("references") or "",
            "to_email_list": _j(d.get("to_json")),
            "cc_email_list": _j(d.get("cc_json")),
            "receive_timestamp": 0,
            "_retry": True,
        })
    return out


# ────────────────────────── 扫描水位 ──────────────────────────
def get_scan_ts(key: str = "inquiry") -> int:
    with _lock:
        conn = _connect()
        try:
            r = conn.execute(
                "SELECT state_value FROM procurement_agent_state WHERE state_key=?",
                ("scan_ts:%s" % key,)).fetchone()
            try:
                return int(r["state_value"] or 0) if r else 0
            except Exception:
                return 0
        finally:
            conn.close()


def set_scan_ts(ts: int, key: str = "inquiry"):
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO procurement_agent_state (state_key, state_value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,"
                " updated_at=excluded.updated_at",
                ("scan_ts:%s" % key, str(int(ts or 0)), _now()))
            conn.commit()
        finally:
            conn.close()


# ────────────────────────── 审计（→ 业务操作日志） ──────────────────────────
def audit(biz_type, biz_id, action, operator=None, snapshot=None, remark=""):
    body = remark or ""
    if snapshot:
        try:
            body = (body + " " + json.dumps(snapshot, ensure_ascii=False)[:900]).strip()
        except Exception:
            pass
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO procurement_op_log (task_id, operator, action, action_time, remark)"
                " VALUES (?,?,?,?,?)",
                (str(biz_id or ""), str(operator or "emp-009"), str(action or ""), _now(), body[:900]))
            conn.commit()
        finally:
            conn.close()


def list_audit(biz_type=None, biz_id=None, limit=200):
    with _lock:
        conn = _connect()
        try:
            if biz_id:
                rows = conn.execute(
                    "SELECT * FROM procurement_op_log WHERE task_id=? ORDER BY id DESC LIMIT ?",
                    (biz_id, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM procurement_op_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ───────────────── 本体专属能力：业务化后降级为 no-op ─────────────────
def record_alignment(*_a, **_kw):
    """对齐记录属本体 ABox 概念，业务链路无需落库。"""
    return None


def list_alignment(limit=200):
    return []


def person_map():
    return {}


def register_person(name, email, role):
    return None
