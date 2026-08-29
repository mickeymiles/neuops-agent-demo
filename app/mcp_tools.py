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


def _proc_mail_cfg():
    """解析邮件/飞书凭据：DB spare_mail_config 优先，缺失时兜底 config/.env。

    返回 dict，含 mail_username/mail_password/feishu_app_id/... 等聚合键。
    DB 不可用或未配置时静默回退到环境变量（emp-008 行为保持不变）。
    """
    cfg = {
        "mail_username": _proc_cfg.PROC_MAIL_USERNAME,
        "mail_password": _proc_cfg.PROC_MAIL_PASSWORD,
        "imap_host": _proc_cfg.PROC_MAIL_IMAP_HOST,
        "imap_port": _proc_cfg.PROC_MAIL_IMAP_PORT,
        "smtp_host": _proc_cfg.PROC_MAIL_SMTP_HOST,
        "smtp_port": _proc_cfg.PROC_MAIL_SMTP_PORT,
        "feishu_app_id": _proc_cfg.PROC_FEISHU_APP_ID,
        "feishu_app_secret": _proc_cfg.PROC_FEISHU_APP_SECRET,
        "feishu_pm_open_id": _proc_cfg.PROC_FEISHU_PM_OPEN_ID,
        "feishu_bitable_app_token": _proc_cfg.PROC_FEISHU_BITABLE_APP_TOKEN,
        "feishu_bitable_task_table_id": _proc_cfg.PROC_FEISHU_BITABLE_TASK_TABLE_ID,
        "feishu_bitable_ledger_table_id": _proc_cfg.PROC_FEISHU_BITABLE_LEDGER_TABLE_ID,
    }
    try:
        from app.db import spare_mail as _spm
        db_cfg = _spm.spare_mail_get_config("proc_credentials") or {}
        if isinstance(db_cfg, dict):
            for k, v in db_cfg.items():
                if v not in (None, "") and k in cfg:
                    cfg[k] = v
    except Exception:
        pass  # DB 不可用 → 保持环境变量兜底
    return cfg


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


def tool_read_inbox_mail(since_timestamp: int = 0, filter_sender_email_list: list = None,
                         exclude_sender_email_list: list = None,
                         match_in_reply_to_msg_ids: list = None,
                         use_unseen: bool = False) -> dict:
    """读取 163 邮箱收件箱入站邮件（IMAP 真实拉取）

    Args:
        since_timestamp: Unix 时间戳，读取该时间之后的邮件（use_unseen=False 时必填）
        filter_sender_email_list: 可选，按发件人邮箱白名单过滤；为空则不过滤
        exclude_sender_email_list: 可选，按发件人邮箱黑名单过滤（采购方自己的邮箱）
        match_in_reply_to_msg_ids: 可选，只读取 In-Reply-To / References 命中
            这些 RFC Message-ID 的邮件（用于精确匹配到某封询价邮件的回复，避免串任务）
        use_unseen: True=只读未读邮件（UNSEEN 搜索），用于 tick 增量；False=SINCE 日期窗口
    Returns:
        邮件报文列表，含 in_reply_to / references 字段用于线程匹配
    """
    import imaplib
    import re  # 【修复 2026-08-24】原代码使用了 re.split/re.sub/re.match 但未导入 re，导致 NameError: name 're' is not defined

    _mc = _proc_mail_cfg()
    if not _mc["mail_password"]:
        return {"tool": "read_inbox_mail", "success": False,
                "error": "PROC_MAIL_PASSWORD 未配置（163 邮箱授权码）", "mails": []}

    # 黑名单默认：采购方自己的 163 邮箱（防止 Sent 副本/自己发的询价邮件误当供应商回复）
    if exclude_sender_email_list is None:
        exclude_sender_email_list = []
    exclude_set = {str(e).lower().strip() for e in exclude_sender_email_list if e}
    if _mc["mail_username"]:
        exclude_set.add(str(_mc["mail_username"]).lower().strip())

    # 询价函关键字（采购方模板：询价函开头一定会出现的语句）——如果原文里出现这些，
    # 直接判为采购方询价函，不是供应商的报价回复
    INQUIRY_KEYWORDS = ("尊敬的供应商", "现就以下备品备件进行询价", "烦请贵司于", "报价截止",
                        "请在回复邮件中注明产品型号、单价", "备品备件询价")

    try:
        imap = imaplib.IMAP4_SSL(_mc["imap_host"], int(_mc["imap_port"] or 993))
        imap.login(_mc["mail_username"], _mc["mail_password"])
        # 163 邮箱要求 login 后立即发送 IMAP ID 命令，否则 SELECT 报 "Unsafe Login"
        # 用 _simple_command 发送（imap.id() 在 Python 3.9 会因 untagged response 报错）
        imaplib.Commands["ID"] = ("AUTH",)
        try:
            imap._simple_command("ID",
                '("name" "NeuOps" "version" "1.0.0" "vendor" "NeuOps" '
                '"support-email" "' + _mc["mail_username"] + '")')
        except Exception:
            pass  # ID 命令响应解析异常不影响命令已发送
        sel_status, sel_data = imap.select("INBOX")
        if sel_status != "OK":
            return {"tool": "read_inbox_mail", "success": False,
                    "error": f"IMAP select INBOX 失败: {sel_status} {sel_data}", "mails": []}

        # IMAP 搜索：UNSEEN（增量 tick）或 SINCE 日期窗口（全量恢复）
        if use_unseen:
            status, data = imap.search(None, "UNSEEN")
        else:
            from datetime import datetime
            since_dt = datetime.fromtimestamp(since_timestamp)
            imap_date = since_dt.strftime("%d-%b-%Y")
            status, data = imap.search(None, f'SINCE {imap_date}')
        if status != "OK":
            return {"tool": "read_inbox_mail", "success": False,
                    "error": f"IMAP search 失败: {status}", "mails": []}

        # RFC Message-ID 规范化（剥掉前后 <>），用于 References/In-Reply-To 比较
        def _norm_mid(m):
            if not m: return ""
            s = str(m).strip()
            while s.startswith("<"): s = s[1:]
            while s.endswith(">"): s = s[:-1]
            return s.strip()
        match_set = {_norm_mid(m) for m in (match_in_reply_to_msg_ids or []) if m}

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
            # 黑名单：排除采购方自己的邮箱（防止把 Sent 副本当成供应商回复）
            if from_email.lower() in exclude_set:
                continue
            # 白名单：按发件人过滤
            if filter_sender_email_list:
                if from_email.lower() not in [e.lower() for e in filter_sender_email_list]:
                    continue

            body = _parse_mail_body(msg)
            rfc_msg_id = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To", "") or ""
            references = msg.get("References", "") or ""

            # —— 过滤 1：如果提供了"询价邮件 msg_id 集合"，只处理对应线程的回复 ——
            if match_set:
                hit_ids = set()
                for raw_ref in [in_reply_to, references]:
                    if raw_ref:
                        # References 可能是一串用空格/换行分隔的 <msg-id>
                        for part in re.split(r"\s+", str(raw_ref).strip()):
                            n = _norm_mid(part)
                            if n and n in match_set:
                                hit_ids.add(n)
                if not hit_ids:
                    # 没有命中线程 → 直接丢弃（避免供应商对其他无关邮件的回复串进来）
                    continue

            # —— 过滤 2：询价函关键字（采购方发的邮件正文一定是询价函模板，供应商回复不会重复这些）——
            body_nolabel = re.sub(r"\s+", "", body or "")[:1200]
            if body_nolabel and any(re.sub(r"\s+", "", k) in body_nolabel for k in INQUIRY_KEYWORDS):
                # 极端情况：供应商直接原文回复"尊敬的供应商：..."可能也被误杀，
                # 但同时带 Re:/回复： 的放行（真实报价回复）
                is_reply = bool(re.match(r"^\s*(re|回复|fw|转发)\s*[:：]", subject, re.I))
                if not is_reply:
                    continue

            out.append({
                "mail_id": mid.decode() if isinstance(mid, bytes) else str(mid),
                "message_id": rfc_msg_id,  # RFC 2822 Message-ID，用于邮件线程回复
                "in_reply_to": in_reply_to,
                "references": references,
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
                   reply_to_mail_id: str = None,
                   reply_refs_chain: str = None) -> dict:
    """发送单封邮件（SMTP 真实发送，163 邮箱）
    reply_to_mail_id: 邮件线程 Message-ID，设置后邮件为该邮件的回复（In-Reply-To+References）
    reply_refs_chain : 上游完整 References 链（空格分隔的 msg_id 串）。设置则 REFs = chain + reply_to_mail_id；
                       不传则 REFs 只写 reply_to_mail_id（向后兼容，但若上游有多层会断链）。
    【修复 2026-08-24】显式调用 email.utils.make_msgid() 生成 Message-ID 并写入邮件头，
    以便返回给调用方用于后续 In-Reply-To 匹配；之前未写入该头导致返回空 message_id="""
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import formataddr, make_msgid

    _mc = _proc_mail_cfg()
    if not _mc["mail_password"]:
        return {"tool": "send_mail", "success": False,
                "error": "PROC_MAIL_PASSWORD 未配置（163 邮箱授权码）"}

    try:
        msg = MIMEText(body_text, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("备品备件采购智能体", _mc["mail_username"]))
        msg["To"] = ",".join(to)
        msg["Message-ID"] = make_msgid()
        if cc:
            msg["Cc"] = ",".join(cc)
        # 邮件线程化：回复时设置 In-Reply-To + 完整 References 链
        if reply_to_mail_id:
            msg["In-Reply-To"] = reply_to_mail_id
            if reply_refs_chain:
                # 上游链 + 当前回复 msg_id → 完整 RFC 会话链
                msg["References"] = f"{reply_refs_chain} {reply_to_mail_id}".strip()
            else:
                msg["References"] = reply_to_mail_id

        recipients = list(to) + (cc or [])
        with smtplib.SMTP_SSL(_mc["smtp_host"], int(_mc["smtp_port"] or 465)) as smtp:
            smtp.login(_mc["mail_username"], _mc["mail_password"])
            smtp.sendmail(_mc["mail_username"], recipients, msg.as_string())

        return {"tool": "send_mail", "success": True,
                "message_id": msg["Message-ID"] or "",
                "reply_to": reply_to_mail_id or "",
                "refs_chain": msg.get("References", "") or "",
                "to": to, "subject": subject}
    except Exception as e:
        return {"tool": "send_mail", "success": False,
                "error": f"SMTP 异常: {type(e).__name__}: {e}"}


def tool_batch_send_mail(receiver_email_list: list, subject: str, body_text: str,
                         cc: list = None, reply_to_mail_id: str = None,
                         reply_refs_chain: str = None) -> dict:
    """批量发送相同内容邮件给多个收件人（独立发送，非群发；每封邮件都带同样的 CC）
    返回 sent 列表，含每个收件人的 message_id（用于后续按邮件线程匹配供应商回复）
    reply_refs_chain 透传到 tool_send_mail，保证每封都带完整 References 链"""
    fail_list, ok_count, sent_list = [], 0, []
    for addr in receiver_email_list:
        r = tool_send_mail(to=[addr], subject=subject, body_text=body_text, cc=cc,
                           reply_to_mail_id=reply_to_mail_id,
                           reply_refs_chain=reply_refs_chain)
        if r.get("success"):
            ok_count += 1
            sent_list.append({"email": addr, "message_id": r.get("message_id") or "",
                              "subject": subject})
        else:
            fail_list.append({"email": addr, "error": r.get("error", "unknown")})
    return {
        "tool": "batch_send_mail", "success": not fail_list,
        "total_count": len(receiver_email_list),
        "success_count": ok_count,
        "fail_email_list": fail_list,
        "cc": cc or [],
        "sent": sent_list,
    }


# ── 飞书 API：tenant_access_token 缓存（2 小时过期）──
_FEISHU_TOKEN_CACHE = {"token": "", "expires_at": 0}


def _get_feishu_token() -> str:
    """获取并缓存飞书 tenant_access_token"""
    if _FEISHU_TOKEN_CACHE["token"] and _time.time() < _FEISHU_TOKEN_CACHE["expires_at"]:
        return _FEISHU_TOKEN_CACHE["token"]
    _fc = _proc_mail_cfg()
    if not _fc["feishu_app_id"] or not _fc["feishu_app_secret"]:
        return ""
    try:
        r = httpx.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                       json={"app_id": _fc["feishu_app_id"],
                             "app_secret": _fc["feishu_app_secret"]}, timeout=10)
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
    """向飞书用户发送 Interactive Card（schema 2.0 = type:raw 格式）
    飞书卡片回调（card.action.trigger）响应要求两端使用同一 schema：
      - 【发送卡片】content 必须是 json.dumps({"type":"raw", "data": <原始卡片 dict>})
      - 【回调响应】返回的 card 字段也必须是 {"type":"raw", "data": <更新后卡片 dict>}
    如果发送端用旧版裸 card、回调端用新版 type:raw（或反过来），会触发 200341 卡片解析失败。

    入参 card：原始卡片结构 {config, header:{title,template}, elements:[...]}
    """
    token = _get_feishu_token()
    if not token:
        return {"tool": "send_feishu_card", "success": False, "error": "飞书 token 获取失败"}
    if not receiver_feishu_open_id:
        return {"tool": "send_feishu_card", "success": False, "error": "open_id 未提供"}

    try:
        # 统一 schema 2.0：把原始卡片包一层 type:raw，才能确保按钮回调能以 type:raw 方式返回更新卡片
        content_payload = {"type": "raw", "data": card}
        r = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": receiver_feishu_open_id,
                "msg_type": "interactive",
                "content": json.dumps(content_payload, ensure_ascii=False),
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
    "procurement_supplier": "procurement_supplier",
    "procurement_contract": "procurement_contract",
    "procurement_contract_supplier": "procurement_contract_supplier",
    "procurement_mail_cc": "procurement_mail_cc",
    "procurement_spare_part": "procurement_spare_part",  # 备件库（skill-proc-chat 对话选型用）
    "project_contract_master": "procurement_master_data",  # 兼容业务文档命名
    "task_table": "procurement_task",  # 兼容设计文档伪代码命名
    "ledger_table": "procurement_ledger",
}


def _pick_pk(table_name: str) -> str:
    """按表给主键名，支持 INSERT/UPDATE/UPSERT 的 WHERE 子句"""
    mapping = {
        "procurement_task": "task_id",
        "procurement_ledger": "ledger_id",
        "procurement_master_data": "id",
        "procurement_op_log": "id",
        "procurement_supplier": "id",
        "procurement_contract": "id",
        "procurement_contract_supplier": "id",
        "procurement_mail_cc": "id",
        "procurement_spare_part": "id",
    }
    return mapping.get(table_name, "id")


def tool_table_query(table_key: str, filter: dict = None, page_size: int = 100,
                     keyword: str = "", keyword_fields: list = None) -> dict:
    """查询 9006 SQLite 表数据。
    keyword: 可选的关键字模糊搜索（对 keyword_fields 做 LIKE %kw% 匹配）。
    keyword_fields: 可选的搜索字段列表（不传时默认为表中所有 TEXT 列）。
    """
    tname = _PROC_TABLE_MAP.get(table_key, table_key)
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        sql = f"SELECT * FROM {tname}"
        params = []
        wheres = []
        if filter:
            for k, v in filter.items():
                wheres.append(f"{k} = ?")
                params.append(v)
        # 关键字模糊搜索
        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            if keyword_fields:
                search_cols = keyword_fields
            else:
                # 自动探测 TEXT 列作为搜索字段
                cur.execute(f"PRAGMA table_info({tname})")
                search_cols = [row[1] for row in cur.fetchall() if row[2].upper() == "TEXT"]
            if search_cols:
                kw_clauses = [f"{c} LIKE ?" for c in search_cols]
                wheres.append("(" + " OR ".join(kw_clauses) + ")")
                params.extend([like] * len(kw_clauses))
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
    """更新 9006 SQLite 表指定行。自动过滤不存在的列，防止静默失败。"""
    tname = _PROC_TABLE_MAP.get(table_key, table_key)
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        # 自动过滤不存在的列，防止 UPDATE 因列不存在而整体失败
        existing_cols = {c[1] for c in cur.execute(f"PRAGMA table_info({tname})").fetchall()}
        filtered = {k: v for k, v in data.items() if k in existing_cols}
        skipped = [k for k in data.keys() if k not in existing_cols]
        if not filtered:
            conn.close()
            return {"tool": "table_update", "success": False, "affected": 0,
                    "error": f"无有效列可更新（{len(data)}个字段均不存在于表 {tname}）"}
        sets = ",".join([f"{k} = ?" for k in filtered.keys()])
        params = list(filtered.values()) + [record_id]
        pk = _pick_pk(tname)
        sql = f"UPDATE {tname} SET {sets} WHERE {pk} = ?"
        cur.execute(sql, params)
        conn.commit()
        affected = cur.rowcount
        conn.close()
        result = {"tool": "table_update", "success": affected > 0, "affected": affected}
        if skipped:
            result["skipped_cols"] = skipped  # 告知调用方哪些列被跳过了
        return result
    except Exception as e:
        return {"tool": "table_update", "success": False,
                "error": f"SQLite 更新失败: {type(e).__name__}: {e}"}


def tool_table_upsert(table_key: str, record_id: str, data: dict) -> dict:
    """表幂等插入或更新：主键存在则更新，不存在则插入"""
    tname = _PROC_TABLE_MAP.get(table_key, table_key)
    pk = _pick_pk(tname)
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM {tname} WHERE {pk} = ? LIMIT 1", (record_id,))
        exists = cur.fetchone() is not None
        if exists:
            sets = ",".join([f"{k} = ?" for k in data.keys()])
            params = list(data.values()) + [record_id]
            cur.execute(f"UPDATE {tname} SET {sets} WHERE {pk} = ?", params)
            mode = "update"
        else:
            merged = dict(data)
            merged[pk] = record_id
            cols = list(merged.keys())
            placeholders = ",".join(["?"] * len(cols))
            cur.execute(
                f"INSERT INTO {tname} ({','.join(cols)}) VALUES ({placeholders})",
                list(merged.values()),
            )
            mode = "insert"
        conn.commit()
        conn.close()
        return {"tool": "table_upsert", "success": True, "mode": mode, "record_id": record_id}
    except Exception as e:
        return {"tool": "table_upsert", "success": False,
                "error": f"SQLite upsert 失败: {type(e).__name__}: {e}"}


def tool_procurement_parse_quote(body: str, expected_qty: int = None, spare_part_model: str = "") -> dict:
    """MCP 包装：6 层加固供应商报价解析"""
    from .routes_procurement_agent import robust_parse_supplier_quote
    return {"tool": "procurement_parse_quote", "success": True,
            "result": robust_parse_supplier_quote(body, expected_qty=expected_qty,
                                                  spare_part_model=spare_part_model)}


def tool_procurement_parse_logistics(body: str) -> dict:
    """MCP 包装：3 层物流单号解析"""
    from .routes_procurement_agent import robust_parse_logistics_info
    return {"tool": "procurement_parse_logistics", "success": True,
            "result": robust_parse_logistics_info(body)}


def tool_procurement_create_task(*, project_id: str = "", project_name: str = "",
                                 contract_no: str = "",
                                 spare_part_model: str, purchase_qty: float,
                                 emergency_level: str,
                                 inquiry_supplier_list: list = None,
                                 creator: str = "agent") -> dict:
    """MCP 工具：创建询比价采购任务（对话入口专用）。

    不走直连 SQLite，而是调 9006 的 POST /api/procurement/tasks/agent：
    - 保证 task_id 格式（PROC-YYYYMMDDHHMMSS-XXXXXX）
    - 自动计算 reply_deadline、写操作日志
    - 自动 trigger_neuops → flow-proc-01/02（询价邮件+飞书通知）

    inquiry_supplier_list 语义：
    - None（默认）→ 9006 后端自动带全量资源池（3家默认供应商）
    - 空列表 [] → 同上，自动带全量资源池
    - 有元素的列表 → 使用指定供应商（资源池供应商+临时供应商混合传也可以，9006 create_task 会按 email 反查补 id）
    """
    try:
        url = f"{_proc_cfg.PROC_9006_BASE}/api/procurement/tasks/agent"
        payload = {
            "project_id": project_id,
            "project_name": project_name,
            "contract_no": contract_no,
            "spare_part_model": spare_part_model,
            "purchase_qty": float(purchase_qty),
            "emergency_level": emergency_level,
            "creator": creator,
        }
        # inquiry_supplier_list: None 和 [] 统一不传，让 9006 后端走自动带池分支
        if inquiry_supplier_list:
            payload["inquiry_supplier_list"] = inquiry_supplier_list
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=payload)
        if r.status_code != 200:
            return {"tool": "procurement_create_task", "success": False,
                    "error": f"9006 创建任务失败 HTTP {r.status_code}: {r.text[:300]}"}
        data = r.json()
        if not data.get("success"):
            return {"tool": "procurement_create_task", "success": False,
                    "error": data.get("error", "9006 返回失败")}
        task = data.get("data") or {}
        return {
            "tool": "procurement_create_task",
            "success": True,
            "task_id": task.get("task_id"),
            "task": task,
            "agent_trigger": data.get("agent_trigger"),
            "reply_deadline": task.get("reply_deadline"),
            "task_status": task.get("task_status"),
        }
    except Exception as e:
        return {"tool": "procurement_create_task", "success": False,
                "error": f"创建任务异常: {type(e).__name__}: {e}"}


# ════════════════════════════════════════════════════════════════
# 采购对话辅助查询工具（给 skill-proc-chat 用，LLM 对话式收集信息时调用）
# ════════════════════════════════════════════════════════════════

def tool_procurement_query_contract(keyword: str = "") -> dict:
    """查询可用合同列表（用于对话中给用户列出选项）。
    keyword: 可选的合同编号/名称关键字（模糊匹配）。空则返回全部合同。
    返回: {contract_no, contract_name, pm_name, pm_email, receiver_name, receiver_phone, receiver_address}
    """
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            cur.execute("""
                SELECT id, contract_no, contract_name, pm_name, pm_email,
                       receiver_name, receiver_phone, receiver_address
                FROM procurement_contract
                WHERE contract_no LIKE ? OR contract_name LIKE ?
                ORDER BY id LIMIT 20
            """, (like, like))
        else:
            cur.execute("""
                SELECT id, contract_no, contract_name, pm_name, pm_email,
                       receiver_name, receiver_phone, receiver_address
                FROM procurement_contract
                ORDER BY id LIMIT 20
            """)
        rows = []
        for r in cur.fetchall():
            rows.append({
                "id": r[0],
                "contract_no": r[1],
                "contract_name": r[2],
                "pm_name": r[3],
                "pm_email": r[4],
                "receiver_name": r[5] or "",
                "receiver_phone": r[6] or "",
                "receiver_address": r[7] or "",
            })
        conn.close()
        return {"tool": "procurement_query_contract", "success": True, "records": rows, "total": len(rows)}
    except Exception as e:
        return {"tool": "procurement_query_contract", "success": False,
                "error": f"查询合同失败: {type(e).__name__}: {e}", "records": [], "total": 0}


def tool_procurement_query_spare_part(keyword: str = "") -> dict:
    """查询可用备件型号列表（用于对话中给用户列出选项）。
    keyword: 可选的备件名称/型号/品牌关键字（模糊匹配）。空则返回全部备件。
    返回: {part_code, part_name, spec_model, brand, unit, category, condition}
    """
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            cur.execute("""
                SELECT id, part_code, part_name, spec_model, brand, unit, category, condition
                FROM procurement_spare_part
                WHERE part_name LIKE ? OR spec_model LIKE ? OR brand LIKE ? OR part_code LIKE ?
                ORDER BY id LIMIT 20
            """, (like, like, like, like))
        else:
            cur.execute("""
                SELECT id, part_code, part_name, spec_model, brand, unit, category, condition
                FROM procurement_spare_part
                ORDER BY id LIMIT 20
            """)
        rows = []
        for r in cur.fetchall():
            rows.append({
                "id": r[0],
                "part_code": r[1],
                "part_name": r[2],
                "spec_model": r[3],
                "brand": r[4],
                "unit": r[5],
                "category": r[6],
                "condition": r[7] or "",
            })
        conn.close()
        return {"tool": "procurement_query_spare_part", "success": True, "records": rows, "total": len(rows)}
    except Exception as e:
        return {"tool": "procurement_query_spare_part", "success": False,
                "error": f"查询备件失败: {type(e).__name__}: {e}", "records": [], "total": 0}


def tool_procurement_query_supplier(keyword: str = "") -> dict:
    """查询资源池供应商列表（用于对话中给用户列出选项）。
    keyword: 可选的供应商名称/邮箱关键字（模糊匹配）。空则返回全部供应商。
    返回: {id, name, email, capability}
    """
    try:
        conn = _proc_db_conn()
        cur = conn.cursor()
        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            cur.execute("""
                SELECT id, name, email, capability
                FROM procurement_supplier
                WHERE name LIKE ? OR email LIKE ?
                ORDER BY id LIMIT 20
            """, (like, like))
        else:
            cur.execute("""
                SELECT id, name, email, capability
                FROM procurement_supplier
                ORDER BY id LIMIT 20
            """)
        rows = []
        for r in cur.fetchall():
            rows.append({
                "id": r[0],
                "name": r[1],
                "email": r[2],
                "capability": r[3] or "",
            })
        conn.close()
        return {"tool": "procurement_query_supplier", "success": True, "records": rows, "total": len(rows)}
    except Exception as e:
        return {"tool": "procurement_query_supplier", "success": False,
                "error": f"查询供应商失败: {type(e).__name__}: {e}", "records": [], "total": 0}

