# -*- coding: utf-8 -*-
"""「备件邮件询价」→ contract-compare(9006) 平台库的同步写入层。

最小闭环：mail-inquiry 引擎的主库仍是 neuops_sessions.db（spare_mail_task），
但在任务 create/update 时，把同一任务 upsert 到 contract-9006 的
contract_compare.db.mail_inquiry_task，供 9006 平台页面观察/配置。

表结构 mail_inquiry_task 与 spare_mail_task 对齐（双流字段齐全），
额外含 mail_archive_json（关键邮件全文落库）与 from_email 等展示字段。
"""

import json
import os
import sqlite3
from datetime import datetime

# contract 库路径：与 app/config.PROC_9006_DB_PATH 保持一致（从环境或默认推导）
_DEFAULT_9006_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "contract-compare", "contract_compare.db",
)


def _contract_db_path() -> str:
    return os.getenv("PROC_9006_DB_PATH", _DEFAULT_9006_DB)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# mail_inquiry_task 的列：对齐 spare_mail_task + 展示/归档增强
_MAIL_TASK_COLS = (
    "task_id", "project_no", "project_name", "part_type", "brand", "pn", "spec",
    "condition", "count", "address", "urgent", "inquiry_deadline",
    "suppliers_json", "quotes_json", "lowest_supplier", "lowest_quote",
    "approval_state", "approval_result", "approver_email", "target_supplier",
    "internal_status", "external_status", "status", "shipped_no",
    "latest_step", "thread_msg_id", "from_email",
    "mail_archive_json", "created_at", "updated_at",
)


def _ensure_table(conn) -> None:
    """幂等建表（contract 库不常用该表时也能直接建）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mail_inquiry_task (
            task_id TEXT PRIMARY KEY,
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
            inquiry_deadline TEXT DEFAULT '',
            suppliers_json TEXT DEFAULT '[]',
            quotes_json TEXT DEFAULT '[]',
            lowest_supplier TEXT DEFAULT '',
            lowest_quote TEXT DEFAULT '',
            approval_state TEXT DEFAULT '',
            approval_result TEXT DEFAULT '',
            approver_email TEXT DEFAULT '',
            target_supplier TEXT DEFAULT '',
            internal_status TEXT DEFAULT '',
            external_status TEXT DEFAULT '',
            status TEXT DEFAULT '',
            shipped_no TEXT DEFAULT '',
            latest_step TEXT DEFAULT '',
            thread_msg_id TEXT DEFAULT '',
            from_email TEXT DEFAULT '',
            mail_archive_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
    """)


def contract_mail_upsert(task: dict, patch: dict = None) -> bool:
    """把 mail-inquiry 任务 upsert 到 contract-9006 平台库（mail_inquiry_task）。

    task：新建/完整任务快照；patch：增量更新（可选）。
    contract 库不可达时静默失败（不影响 neuops 主流程）。
    """
    try:
        path = _contract_db_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            _ensure_table(conn)
            # 取现有行（若已有），merge 增量
            existing = conn.execute(
                "SELECT * FROM mail_inquiry_task WHERE task_id=?", (task.get("task_id"),)
            ).fetchone()
            base = dict(existing) if existing else {}
            merged = dict(base)
            merged.update({k: v for k, v in (task or {}).items() if k in _MAIL_TASK_COLS})
            if patch:
                merged.update({k: v for k, v in patch.items() if k in _MAIL_TASK_COLS})
            merged.setdefault("task_id", task.get("task_id"))
            if not merged.get("task_id"):
                return False
            merged["updated_at"] = _now()
            if not merged.get("created_at"):
                merged["created_at"] = merged["updated_at"]

            cols = [k for k in _MAIL_TASK_COLS if k in merged]
            vals = [merged[k] for k in cols]
            # 若为 json 结构字段，序列化
            for cidx, c in enumerate(cols):
                if c in ("suppliers_json", "quotes_json", "lowest_quote", "mail_archive_json"):
                    if isinstance(vals[cidx], (dict, list)):
                        vals[cidx] = json.dumps(vals[cidx], ensure_ascii=False)
            ph = ",".join(["?"] * len(cols))
            sets = ",".join([f"{c}=excluded.{c}" for c in cols if c != "task_id"])
            conn.execute(
                f"INSERT INTO mail_inquiry_task ({','.join(cols)}) VALUES ({ph}) "
                f"ON CONFLICT(task_id) DO UPDATE SET {sets}",
                vals,
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"[contract_mail] sync to 9006 db failed: {e}")
        return False


def contract_mail_archive_append(task_id: str, mail: dict) -> bool:
    """把一封关键邮件全文追加进 mail_archive_json（供页面查看历史原文/To/Cc）。"""
    try:
        path = _contract_db_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT mail_archive_json FROM mail_inquiry_task WHERE task_id=?", (task_id,)
            ).fetchone()
            arr = []
            if row and row["mail_archive_json"]:
                try:
                    arr = json.loads(row["mail_archive_json"])
                except Exception:
                    arr = []
            arr.append(mail)
            conn.execute(
                "UPDATE mail_inquiry_task SET mail_archive_json=?, updated_at=? WHERE task_id=?",
                (json.dumps(arr, ensure_ascii=False), _now(), task_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"[contract_mail] archive append failed: {e}")
        return False