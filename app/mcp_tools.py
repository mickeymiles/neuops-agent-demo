# -*- coding: utf-8 -*-
"""MCP 工具层：请求模型 + 6 个 Mock MCP 工具 + 6 个 emp-008 真实采购 MCP 工具"""
import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
from pydantic import BaseModel

from mock_data import MOCK_ALARMS, MOCK_CHANGES, MOCK_CMDB, MOCK_LOGS, MOCK_METRICS


class ChatRequest(BaseModel):
    query: str
    conversation_id: str = ""
    mode: str = "free"       # "free" | "skill"
    selected_skill: str = "" # skill id when mode=skill
    enabled_skills: list = []
    approved_action: Optional[str] = None  # 审批确认后携带
    engine: str = ""         # "" = 用 config.AGENT_ENGINE；可选 "legacy" | "dsh"

# ────────────────────────────────────────────
# Mock MCP Tool Handlers
# ────────────────────────────────────────────

def tool_get_business_metric(service: str = "order-service", metric: str = "all") -> dict:
    data = MOCK_METRICS.get(service, MOCK_METRICS["order-service"])
    timestamps = [(datetime.now() - timedelta(minutes=5*i)).strftime("%H:%M") for i in range(7, 0, -1)]
    return {
        "tool": "get_business_metric",
        "service": service,
        "metric": metric,
        "data": {
            "timestamps": timestamps,
            "metrics": data,
            "summary": f"{service} P99延迟从 {data['latency_p99'][0]}ms 上升至 {data['latency_p99'][-1]}ms，增幅 {round((data['latency_p99'][-1]/data['latency_p99'][0]-1)*100)}%；错误率从 {data['error_rate'][0]}% 升至 {data['error_rate'][-1]}%"
        }
    }

def tool_search_service_log(service: str = "order-service", level: str = "ERROR") -> dict:
    logs = [l for l in MOCK_LOGS if l["service"] == service and (level == "ALL" or l["level"] == level)]
    return {
        "tool": "search_service_log",
        "service": service,
        "level": level,
        "total": len(logs),
        "logs": logs,
    }

def tool_query_cmdb_topology(app: str = "order-service") -> dict:
    """优先返回真实运维本体数据；真实数据不足时回退到 MOCK_CMDB 兜底"""
    from . import ops_ontology
    topo = ops_ontology.build_topology()
    nodes = topo.get("nodes", [])
    # 若本体无数据，则回退到旧 mock 数据保持兼容性
    if not nodes:
        data = MOCK_CMDB.get(app, MOCK_CMDB["order-service"])
        return {"tool": "query_cmdb_topology", "app": app, "data": data, "source": "mock"}
    # 尝试按应用名过滤子图
    app_nodes = [n for n in nodes if app.lower() in n.get("name", "").lower()]
    if not app_nodes:
        app_nodes = nodes
    ids = {n["id"] for n in app_nodes}
    edges = [e for e in topo.get("edges", []) if e["source"] in ids or e["target"] in ids]
    return {
        "tool": "query_cmdb_topology",
        "app": app,
        "data": {
            "nodes": app_nodes,
            "edges": edges,
            "summary": topo.get("summary", {}),
        },
        "source": "real",
    }

def tool_query_change_record(service: str = "order-service", hours: int = 24) -> dict:
    changes = MOCK_CHANGES  # all recent enough for demo
    return {
        "tool": "query_change_record",
        "service": service,
        "hours": hours,
        "total": len(changes),
        "changes": changes,
    }

def tool_run_auto_job(job_type: str, target: str) -> dict:
    return {
        "tool": "run_auto_job",
        "job_type": job_type,
        "target": target,
        "status": "success",
        "message": f"自动化作业执行成功：{job_type} → {target}",
        "execution_id": f"JOB-{uuid.uuid4().hex[:8].upper()}",
        "duration": f"{random.uniform(2.5, 8.0):.1f}s",
    }

def tool_query_alarm_info(service: str = "order-service") -> dict:
    alarms = [a for a in MOCK_ALARMS if a["service"] == service]
    return {
        "tool": "query_alarm_info",
        "service": service,
        "total": len(alarms),
        "alarms": alarms,
    }


# ════════════════════════════════════════════════════════════════════
# emp-008 备品备件采购询比价：6 个真实 MCP 工具
# 邮件 IMAP/SMTP（163 邮箱） + 飞书 API + SQLite 表格读写
# ════════════════════════════════════════════════════════════════════
import email as _email_pkg
from email.header import decode_header as _decode_header
import sqlite3 as _sqlite3
import time as _time

from app import config as _proc_cfg


def _decode_mime(s: str) -> str:
    """解码 MIME 编码的邮件头"""
    if not s:
        return ""
    parts = _decode_header(s)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            out.append(txt.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)


def _parse_mail_body(msg) -> str:
    """提取邮件正文（优先 text/plain，其次 text/html 简化）"""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    enc = part.get_content_charset() or "utf-8"
                    return payload.decode(enc, errors="replace")
        # 无 plain，取 html
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    enc = part.get_content_charset() or "utf-8"
                    return payload.decode(enc, errors="replace")
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            enc = msg.get_content_charset() or "utf-8"
            return payload.decode(enc, errors="replace")
        return ""


def tool_read_inbox_mail(since_timestamp: int, filter_sender_email_list: list = None) -> dict:
    """读取 163 邮箱收件箱入站邮件（IMAP 真实拉取）

    Args:
        since_timestamp: Unix 时间戳，读取该时间之后的邮件（必填）
        filter_sender_email_list: 可选，按发件人邮箱过滤；为空则不过滤
    Returns:
        邮件报文列表
    """
    import imaplib

    if not _proc_cfg.PROC_MAIL_PASSWORD:
        return {"tool": "read_inbox_mail", "success": False,
                "error": "PROC_MAIL_PASSWORD 未配置（163 邮箱授权码）", "mails": []}

    try:
        imap = imaplib.IMAP4_SSL(_proc_cfg.PROC_MAIL_IMAP_HOST, _proc_cfg.PROC_MAIL_IMAP_PORT)
        imap.login(_proc_cfg.PROC_MAIL_USERNAME, _proc_cfg.PROC_MAIL_PASSWORD)
        # 163 邮箱要求 login 后立即发送 IMAP ID 命令，否则 SELECT 报 "Unsafe Login"
        # 用 _simple_command 发送（imap.id() 在 Python 3.9 会因 untagged response 报错）
        imaplib.Commands["ID"] = ("AUTH",)
        try:
            imap._simple_command("ID",
                '("name" "NeuOps" "version" "1.0.0" "vendor" "NeuOps" '
                '"support-email" "' + _proc_cfg.PROC_MAIL_USERNAME + '")')
        except Exception:
            pass  # ID 命令响应解析异常不影响命令已发送
        sel_status, sel_data = imap.select("INBOX")
        if sel_status != "OK":
            return {"tool": "read_inbox_mail", "success": False,
                    "error": f"IMAP select INBOX 失败: {sel_status} {sel_data}", "mails": []}

        # IMAP SINCE 搜索（IMAP 日期粒度到天，再用时间戳过滤）
        from datetime import datetime
        since_dt = datetime.fromtimestamp(since_timestamp)
        imap_date = since_dt.strftime("%d-%b-%Y")
        status, data = imap.search(None, f'SINCE {imap_date}')
        if status != "OK":
            return {"tool": "read_inbox_mail", "success": False,
                    "error": f"IMAP search 失败: {status}", "mails": []}

        mail_ids = data[0].split()
        out = []
        for mid in mail_ids:
            status, msg_data = imap.fetch(mid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = _email_pkg.message_from_bytes(raw)
            from_full = _decode_mime(msg.get("From", ""))
            # 提取邮箱
            from_email = ""
            if "<" in from_full and ">" in from_full:
                from_email = from_full[from_full.find("<")+1:from_full.find(">")]
            subject = _decode_mime(msg.get("Subject", ""))
            # 时间戳
            date_str = msg.get("Date", "")
            try:
                from email.utils import parsedate_to_datetime
                recv_dt = parsedate_to_datetime(date_str)
                recv_ts = int(recv_dt.timestamp()) if recv_dt else 0
            except Exception:
                recv_ts = 0

            # 二次过滤：按 since_timestamp 过滤
            if recv_ts and recv_ts < since_timestamp:
                continue
            # 按发件人过滤
            if filter_sender_email_list:
                if from_email.lower() not in [e.lower() for e in filter_sender_email_list]:
                    continue

            body = _parse_mail_body(msg)
            rfc_msg_id = msg.get("Message-ID", "")
            out.append({
                "mail_id": mid.decode() if isinstance(mid, bytes) else str(mid),
                "message_id": rfc_msg_id,  # RFC 2822 Message-ID，用于邮件线程回复
                "subject": subject,
                "from_email": from_email,
                "from_name": from_full.replace(f"<{from_email}>", "").strip().strip('"'),
                "to_email_list": [addr.strip() for addr in msg.get("To", "").split(",")],
                "mail_body_text": body[:5000],  # 截断保护
                "receive_timestamp": recv_ts,
            })

        imap.logout()
        return {"tool": "read_inbox_mail", "success": True, "total": len(out), "mails": out}
    except Exception as e:
        return {"tool": "read_inbox_mail", "success": False,
                "error": f"IMAP 异常: {type(e).__name__}: {e}", "mails": []}


def tool_send_mail(to: list, subject: str, body_text: str, cc: list = None,
                   reply_to_mail_id: str = None) -> dict:
    """发送单封邮件（SMTP 真实发送，163 邮箱）
    reply_to_mail_id: 邮件线程 Message-ID，设置后邮件为该邮件的回复（In-Reply-To+References）
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import formataddr

    if not _proc_cfg.PROC_MAIL_PASSWORD:
        return {"tool": "send_mail", "success": False,
                "error": "PROC_MAIL_PASSWORD 未配置（163 邮箱授权码）"}

    try:
        msg = MIMEText(body_text, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("备品备件采购智能体", _proc_cfg.PROC_MAIL_USERNAME))
        msg["To"] = ",".join(to)
        if cc:
            msg["Cc"] = ",".join(cc)
        # 邮件线程化：回复时设置 In-Reply-To + References
        if reply_to_mail_id:
            msg["In-Reply-To"] = reply_to_mail_id
            msg["References"] = reply_to_mail_id

        recipients = list(to) + (cc or [])
        with smtplib.SMTP_SSL(_proc_cfg.PROC_MAIL_SMTP_HOST, _proc_cfg.PROC_MAIL_SMTP_PORT) as smtp:
            smtp.login(_proc_cfg.PROC_MAIL_USERNAME, _proc_cfg.PROC_MAIL_PASSWORD)
            smtp.sendmail(_proc_cfg.PROC_MAIL_USERNAME, recipients, msg.as_string())

        return {"tool": "send_mail", "success": True,
                "message_id": msg["Message-ID"] or "",
                "reply_to": reply_to_mail_id or "",
                "to": to, "subject": subject}
    except Exception as e:
        return {"tool": "send_mail", "success": False,
                "error": f"SMTP 异常: {type(e).__name__}: {e}"}


def tool_batch_send_mail(receiver_email_list: list, subject: str, body_text: str) -> dict:
    """批量发送相同内容邮件给多个收件人（独立发送，非抄送）"""
    fail_list, ok_count = [], 0
    for addr in receiver_email_list:
        r = tool_send_mail(to=[addr], subject=subject, body_text=body_text)
        if r.get("success"):
            ok_count += 1
        else:
            fail_list.append({"email": addr, "error": r.get("error", "unknown")})
    return {
        "tool": "batch_send_mail", "success": not fail_list,
        "total_count": len(receiver_email_list),
        "success_count": ok_count,
        "fail_email_list": fail_list,
    }


# ── 飞书 API：tenant_access_token 缓存（2 小时过期）──
_FEISHU_TOKEN_CACHE = {"token": "", "expires_at": 0}


def _get_feishu_token() -> str:
    """获取并缓存飞书 tenant_access_token"""
    if _FEISHU_TOKEN_CACHE["token"] and _time.time() < _FEISHU_TOKEN_CACHE["expires_at"]:
        return _FEISHU_TOKEN_CACHE["token"]
    if not _proc_cfg.PROC_FEISHU_APP_ID or not _proc_cfg.PROC_FEISHU_APP_SECRET:
        return ""
    try:
        r = httpx.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                       json={"app_id": _proc_cfg.PROC_FEISHU_APP_ID,
                             "app_secret": _proc_cfg.PROC_FEISHU_APP_SECRET}, timeout=10)
        d = r.json()
        token = d.get("tenant_access_token", "")
        expire = d.get("expire", 7200)
        _FEISHU_TOKEN_CACHE["token"] = token
        _FEISHU_TOKEN_CACHE["expires_at"] = _time.time() + expire - 300  # 提前 5 分钟刷新
        return token
    except Exception:
        return ""


def tool_send_feishu_message(receiver_feishu_open_id: str, content: str, is_alert: bool = False) -> dict:
    """向飞书用户发送文本消息（真实调用飞书 open API）"""
    token = _get_feishu_token()
    if not token:
        return {"tool": "send_feishu_message", "success": False,
                "error": "飞书凭据未配置或获取 token 失败"}
    if not receiver_feishu_open_id:
        return {"tool": "send_feishu_message", "success": False,
                "error": "receiver_feishu_open_id 未提供（项目经理 open_id 未配置）"}

    try:
        r = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": receiver_feishu_open_id,
                "msg_type": "text",
                "content": json.dumps({"text": content}),
            }, timeout=10)
        d = r.json()
        if d.get("code") == 0:
            return {"tool": "send_feishu_message", "success": True,
                    "msg_id": d.get("data", {}).get("message_id", ""), "is_alert": is_alert}
        return {"tool": "send_feishu_message", "success": False,
                "error": f"飞书 API 返回: code={d.get('code')} msg={d.get('msg')}"}
    except Exception as e:
        return {"tool": "send_feishu_message", "success": False,
                "error": f"飞书 API 异常: {type(e).__name__}: {e}"}


def tool_send_feishu_card(receiver_feishu_open_id: str, card: dict) -> dict:
    """向飞书用户发送 Interactive Card（交互卡片，带按钮等元素）
    card 结构参考飞书消息卡片 JSON Schema:
    {config, header:{title,template}, elements:[{tag:div|action|...}]}
    """
    token = _get_feishu_token()
    if not token:
        return {"tool": "send_feishu_card", "success": False, "error": "飞书 token 获取失败"}
    if not receiver_feishu_open_id:
        return {"tool": "send_feishu_card", "success": False, "error": "open_id 未提供"}

    try:
        r = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": receiver_feishu_open_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            }, timeout=10)
        d = r.json()
        if d.get("code") == 0:
            return {"tool": "send_feishu_card", "success": True,
                    "msg_id": d.get("data", {}).get("message_id", "")}
        return {"tool": "send_feishu_card", "success": False,
                "error": f"code={d.get('code')} msg={d.get('msg')}"}
    except Exception as e:
        return {"tool": "send_feishu_card", "success": False,
                "error": f"飞书 API 异常: {type(e).__name__}: {e}"}


# ── SQLite 表格读写（直连 contract-compare-9006 的 contract_compare.db）──
def _proc_db_conn():
    """连接 9006 工程的 SQLite，供 emp-008 直读采购任务/台账/主数据"""
    db_path = _proc_cfg.PROC_9006_DB_PATH
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    return conn


# 表名映射：MCP 语义 table_key → 9006 SQLite 实际表名
_PROC_TABLE_MAP = {
    "procurement_task": "procurement_task",
    "procurement_master_data": "procurement_master_data",
    "procurement_ledger": "procurement_ledger",
    "procurement_op_log": "procurement_op_log",
    "project_contract_master": "procurement_master_data",  # 兼容业务文档命名
    "task_table": "procurement_task",  # 兼容设计文档伪代码命名
    "ledger_table": "procurement_ledger",
}


def tool_table_query(table_key: str, filter: dict = None, page_size: int = 100) -> dict:
    """查询 9006 SQLite 表数据"""
    tname = _PROC_TABLE_MAP.get(table_key, table_key)
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        sql = f"SELECT * FROM {tname}"
        params = []
        if filter:
            wheres = []
            for k, v in filter.items():
                wheres.append(f"{k} = ?")
                params.append(v)
            if wheres:
                sql += " WHERE " + " AND ".join(wheres)
        sql += f" LIMIT {int(page_size)}"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"tool": "table_query", "success": True, "records": rows, "total": len(rows)}
    except Exception as e:
        return {"tool": "table_query", "success": False,
                "error": f"SQLite 查询失败: {type(e).__name__}: {e}", "records": [], "total": 0}


def tool_table_insert(table_key: str, data: dict) -> dict:
    """向 9006 SQLite 表插入单行"""
    tname = _PROC_TABLE_MAP.get(table_key, table_key)
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        cols = list(data.keys())
        placeholders = ",".join(["?"] * len(cols))
        sql = f"INSERT INTO {tname} ({','.join(cols)}) VALUES ({placeholders})"
        cur.execute(sql, list(data.values()))
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        return {"tool": "table_insert", "success": True, "record_id": rid}
    except Exception as e:
        return {"tool": "table_insert", "success": False,
                "error": f"SQLite 插入失败: {type(e).__name__}: {e}"}


def tool_table_update(table_key: str, record_id: str, data: dict) -> dict:
    """更新 9006 SQLite 表指定行"""
    tname = _PROC_TABLE_MAP.get(table_key, table_key)
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        sets = ",".join([f"{k} = ?" for k in data.keys()])
        params = list(data.values()) + [record_id]
        # 主键策略：procurement_task/ledger 用 task_id/ledger_id；master_data 用 id
        pk = "task_id" if tname == "procurement_task" else ("ledger_id" if tname == "procurement_ledger" else "id")
        sql = f"UPDATE {tname} SET {sets} WHERE {pk} = ?"
        cur.execute(sql, params)
        conn.commit()
        affected = cur.rowcount
        conn.close()
        return {"tool": "table_update", "success": affected > 0, "affected": affected}
    except Exception as e:
        return {"tool": "table_update", "success": False,
                "error": f"SQLite 更新失败: {type(e).__name__}: {e}"}

