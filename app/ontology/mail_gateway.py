# -*- coding: utf-8 -*-
"""邮件网关：只读复用现轨 `mcp_tools` 的 tool_send_mail / tool_read_inbox_mail（SKL-R-01）。
本模块只 import 调用，不改动现轨文件；如需修改行为则在此另起实现，绝不写现轨。"""
import time


def read_inbox(since_timestamp: int = 0, filter_sender_email_list=None):
    """只读收件箱。延迟 import 现轨 tool，保持只读复用。"""
    from app.mcp_tools import tool_read_inbox_mail
    return tool_read_inbox_mail(since_timestamp=since_timestamp,
                                filter_sender_email_list=filter_sender_email_list)


def send_mail(to, subject, body_text, cc=None, reply_to_mail_id=None,
              reply_refs_chain=None, reply_all_from=None):
    """发信（Stage B 才启用；Stage A 不调用）。只读复用现轨 tool。"""
    from app.mcp_tools import tool_send_mail
    return tool_send_mail(to=to, subject=subject, body_text=body_text, cc=cc,
                          reply_to_mail_id=reply_to_mail_id,
                          reply_refs_chain=reply_refs_chain,
                          reply_all_from=reply_all_from)


def fetch_unseen_since(hours: int = 1):
    """返回 hours 内的未读/新邮件。"""
    epoch = int(time.time()) - hours * 3600
    return read_inbox(since_timestamp=epoch)


def mark_seen_by_message_id(msg_id: str) -> bool:
    """SEEN 认领握手：按 Message-ID 头定位邮件并置 \\Seen。
    用于灰度时把已由本体轨认领的邮件设为已读，使现轨的 UNSEEN 增量不会重复处理。"""
    if not msg_id:
        return False
    mid = msg_id.strip()
    try:
        import imaplib
        from app.mcp_tools import _proc_mail_cfg
        _mc = _proc_mail_cfg()
        host = _mc.get("imap_host") or _mc.get("mail_imap_host") or "imap.163.com"
        port = int(_mc.get("imap_port") or _mc.get("mail_imap_port") or 993)
        user = _mc.get("mail_username")
        pwd = _mc.get("mail_password")
        if not user or not pwd:
            return False
        c = imaplib.IMAP4_SSL(host, port)
        c.login(user, pwd)
        try:
            c._simple_command("ID", '("name" "E2E-Ont" "vendor" "Run")')
        except Exception:
            pass
        c.select("INBOX")
        typ, data = c.search(None, "HEADER Message-ID", mid)
        nums = (data[0] or b"").split()
        if nums:
            c.store(b",".join(nums), "+FLAGS", "\\Seen")
        c.logout()
        return bool(nums)
    except Exception:
        return False