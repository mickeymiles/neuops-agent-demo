# -*- coding: utf-8 -*-
"""「备件邮件询价」→ contract-compare(9006) 平台库的同步写入层。

统一任务模型：页面 / Agent 对话 / 工程师邮件 三入口共用 procurement_task 表。
本模块负责把 mail-inquiry 引擎（双流）任务 upsert 到 contract-9006 的
contract_compare.db.procurement_task（补列后的双流字段），并归档邮件原文。

procurement_task 需已由 contract 工程补列（internal_status/external_status/
approval_state/approver_email/target_supplier/project_no/brand/pn/spec/
condition/count/address/urgent/inquiry_deadline/mail_archive_json/from_email/
source/latest_ship_time/…），本模块仅写入，不建 contract 主表结构冲突。
"""

import json
import os
import re
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


# contract procurement_task.emergency_level 的合法枚举
_EMERGENCY_ENUM = {"2h", "4h", "5h"}


def _norm_emergency(urgent) -> str:
    """把 spare_mail 的 urgent/询价时限规范成 procurement_task 的 ENUM。
    值可能形如 4h/2h/5h/1h/24h/12h/48h/高/中/低 等；无法归一取 4h。"""
    s = str(urgent or "").strip().lower().replace(" ", "")
    if s in _EMERGENCY_ENUM:
        return s
    m = re.search(r"(\d+)\s*(?:h|小时|hour)", s)
    if m:
        h = int(m.group(1))
        if h <= 2:
            return "2h"
        if h <= 4:
            return "4h"
        if h <= 5:
            return "5h"
        return "5h"
    # 文本紧急程度：高→2h，中→4h，低→5h
    if "高" in s or s in ("urgent", "critical"):
        return "2h"
    if "中" in s or s in ("medium", "normal"):
        return "4h"
    return "4h"


# procurement_task 中本模块会写入的列（缺失时幂等补列，随写随补）
_WRITE_COLS = (
    "task_id", "project_no", "project_name", "part_type", "brand", "pn", "spec",
    "condition", "count", "purchase_qty", "address", "urgent", "inquiry_deadline",
    "suppliers_json", "quotes_json", "lowest_supplier", "lowest_quote",
    "approval_state", "approval_result", "approver_email", "target_supplier",
    "internal_status", "external_status", "shipped_no", "mail_archive_json",
    "from_email", "source", "latest_ship_time", "latest_step",
    # NOT NULL 无默认的既有列，必须显式写入
    "spare_part_model", "contract_no", "creator",
)

# 需要落库为 JSON 的列
_JSON_COLS = ("suppliers_json", "quotes_json", "lowest_quote", "mail_archive_json")


def _ensure_columns(conn) -> None:
    """幂等补列：procurement_task 缺少本模块需要写的列时 ALTER ADD。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(procurement_task)")}
    additions = {
        "project_no": "TEXT DEFAULT ''", "project_name": "TEXT DEFAULT ''",
        "part_type": "TEXT DEFAULT ''", "brand": "TEXT DEFAULT ''", "pn": "TEXT DEFAULT ''",
        "spec": "TEXT DEFAULT ''", "condition": "TEXT DEFAULT ''", "count": "TEXT DEFAULT ''",
        "purchase_qty": "REAL DEFAULT 0", "address": "TEXT DEFAULT ''",
        "urgent": "TEXT DEFAULT ''", "inquiry_deadline": "TEXT DEFAULT ''",
        "suppliers_json": "TEXT DEFAULT '[]'", "quotes_json": "TEXT DEFAULT '[]'",
        "lowest_supplier": "TEXT DEFAULT ''", "lowest_quote": "TEXT DEFAULT ''",
        "approval_state": "TEXT DEFAULT ''", "approval_result": "TEXT DEFAULT ''",
        "approver_email": "TEXT DEFAULT ''", "target_supplier": "TEXT DEFAULT ''",
        "internal_status": "TEXT DEFAULT ''", "external_status": "TEXT DEFAULT ''",
        "shipped_no": "TEXT DEFAULT ''", "mail_archive_json": "TEXT DEFAULT '[]'",
        "from_email": "TEXT DEFAULT ''", "source": "TEXT DEFAULT ''",
        "latest_ship_time": "TEXT DEFAULT ''", "latest_step": "TEXT DEFAULT ''",
    }
    for col, ddl in additions.items():
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE procurement_task ADD COLUMN {col} {ddl}")
                cols.add(col)
            except Exception as e:
                print(f"[contract_mail] add column {col} failed: {e}")


def contract_mail_upsert(task: dict, patch: dict = None) -> bool:
    """把 mail-inquiry 任务 upsert 到 contract procurement_task。

    task：新建/完整任务快照；patch：增量更新（可选）。
    contract 库不可达时静默失败（不影响 neuops 主流程）。
    """
    try:
        path = _contract_db_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            _ensure_columns(conn)
            existing = conn.execute(
                "SELECT * FROM procurement_task WHERE task_id=?", (task.get("task_id"),)
            ).fetchone()
            merged = dict(existing) if existing else {}
            merged.update({k: v for k, v in (task or {}).items() if k in _WRITE_COLS})
            if patch:
                merged.update({k: v for k, v in patch.items() if k in _WRITE_COLS})
            tid = merged.get("task_id") or task.get("task_id")
            if not tid:
                return False
            merged["task_id"] = tid
            merged["updated_at"] = _now()
            # procurement_task 用 create_time 表示创建时间（无 created_at 列），做名归一
            if not merged.get("create_time"):
                merged["create_time"] = merged.get("created_at") or _now()
            # 缺失非空字段置默认（新行 INSERT 需要 NOT NULL 列）
            merged.setdefault("spare_part_model", merged.get("pn") or "")
            merged.setdefault("contract_no", merged.get("project_no") or "")
            merged.setdefault("creator", merged.get("from_email") or "")
            # purchase_qty 为 procurement_task NOT NULL 列，缺省时用 count 映射
            if "purchase_qty" not in merged or merged.get("purchase_qty") in (None, ""):
                try:
                    merged["purchase_qty"] = float(merged.get("count") or 0)
                except Exception:
                    merged["purchase_qty"] = 0
            elif not isinstance(merged.get("purchase_qty"), (int, float)):
                try:
                    merged["purchase_qty"] = float(merged["purchase_qty"])
                except Exception:
                    merged["purchase_qty"] = 0
            # emergency_level / reply_deadline 为 procurement_task NOT NULL 列
            # spare_mail 用 urgent/inquiry_deadline，做映射 + 规范到 ENUM 值
            if not merged.get("emergency_level"):
                merged["emergency_level"] = _norm_emergency(merged.get("urgent"))
            if not merged.get("reply_deadline"):
                merged["reply_deadline"] = merged.get("inquiry_deadline") or _now()
            _WRITE_ALL_COLS = _WRITE_COLS + ("emergency_level", "reply_deadline")
            cols = [k for k in _WRITE_ALL_COLS if k in merged] + ["create_time"]
            vals = list(merged[k] for k in cols)
            # JSON 序列化
            for ci, c in enumerate(cols):
                if c in _JSON_COLS and isinstance(vals[ci], (dict, list)):
                    vals[ci] = json.dumps(vals[ci], ensure_ascii=False)
            ph = ",".join(["?"] * len(cols))
            sets = ",".join([f"{c}=excluded.{c}" for c in cols if c != "task_id"])
            conn.execute(
                f"INSERT INTO procurement_task ({','.join(cols)}) VALUES ({ph}) "
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
            _ensure_columns(conn)
            row = conn.execute(
                "SELECT mail_archive_json FROM procurement_task WHERE task_id=?", (task_id,)
            ).fetchone()
            arr = []
            if row and row["mail_archive_json"]:
                try:
                    arr = json.loads(row["mail_archive_json"])
                except Exception:
                    arr = []
            arr.append(mail)
            conn.execute(
                "UPDATE procurement_task SET mail_archive_json=?, updated_at=? WHERE task_id=?",
                (json.dumps(arr, ensure_ascii=False), _now(), task_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"[contract_mail] archive append failed: {e}")
        return False