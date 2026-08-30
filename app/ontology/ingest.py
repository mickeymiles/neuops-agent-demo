# -*- coding: utf-8 -*-
"""邮箱事实采集：读 IMAP 新邮件 → 幂等入 o_email → 解析为事实上下文 → 新询价建 O_Task。
本体轨用邮箱作为唯一事实源（同现轨），但落 O_* 独立表。
"""
import re
import time


def _clean(v):
    return (v or "").strip().replace("\r", "")


def _field(body, *labels):
    """按标签行提取字段值：'品牌：Seagate' 或 '品牌: Seagate'。"""
    for lb in labels:
        m = re.search(rf"{lb}[：:\s]+([^\n，,；;]+)", body)
        if m:
            return _clean(m.group(1))
    return ""


def parse_inquiry_fields(body: str, subject: str = "") -> dict:
    """从工程师询价邮件正文/主题抽取本体轨事实字段（确定性，不交 LLM）。"""
    text = body or ""
    pno = _field(text, "项目编号", "项目号")
    if not pno:
        m = re.search(r"P(RJ|RJ-)?[A-Z0-9]*-?[0-9A-Z-]+", text + "\n" + subject)
        pno = m.group(0).strip() if m else ""
    return {
        "project_no": pno,
        "project_name": _field(text, "项目名称"),
        "part_type": _field(text, "类型", "备件类型"),
        "brand": _field(text, "品牌"),
        "pn": _field(text, "PN", "PN号", "型号", "料号"),
        "spec": _field(text, "规格"),
        "condition": _field(text, "成色", "新旧"),
        "count": _field(text, "数量"),
        "address": _field(text, "收货地址", "地址"),
        "urgent": _field(text, "紧急程度", "紧急", "时限"),
        "receiver_name": _field(text, "联系人", "收货人"),
        "receiver_phone": _field(text, "电话", "手机"),
    }


def is_inquiry(mail: dict) -> bool:
    """发起判据：非回复(无 in_reply_to/references)、主题非 Re:、含询价关键词。"""
    subject = (mail.get("subject") or "")
    body = (mail.get("mail_body_text") or "") or (mail.get("body") or "")
    if mail.get("in_reply_to") or mail.get("references"):
        return False
    sl = subject.lower()
    if sl.startswith("re:") or sl.startswith("回复") or sl.startswith("re :"):
        return False
    flat = re.sub(r"\s+", "", body + subject)
    return any(kw in flat for kw in ("询价", "采购", "备件", "购买"))


def fetch_new_inquiry_facts(mail_gateway, hours: int = 2, store=None, log=print):
    """读 hours 内新邮件，幂等入库，返回 [ {mail, fields} ] 供决策/建任务。"""
    from . import store as st
    from . import schema
    schema.ensure_core_tables()
    raw = mail_gateway.read_inbox(since_timestamp=int(time.time()) - hours * 3600)
    mails = (raw or {}).get("mails", []) if isinstance(raw, dict) else (raw or [])
    out = []
    for m in mails:
        if not is_inquiry(m):
            continue
        inserted = st.upsert_email({
            "email_message_id": m.get("message_id"),
            "title": m.get("subject"),
            "body": m.get("mail_body_text") or m.get("body"),
            "from_email": m.get("from_email"),
            "to_email_list": m.get("to_email_list") or [],
            "cc_email_list": m.get("cc_email_list") or [],
            "in_reply_to": m.get("in_reply_to"),
            "references": m.get("references"),
            "template_type": "A",
        })
        if not inserted:
            continue  # 已幂等入库，不重复
        fields = parse_inquiry_fields(m.get("mail_body_text") or "", m.get("subject") or "")
        fields["message_id"] = (m.get("message_id") or "").strip()
        fields["from_email"] = (m.get("from_email") or "").strip()
        fields["receive_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        out.append({"mail": m, "fields": fields})
    return out