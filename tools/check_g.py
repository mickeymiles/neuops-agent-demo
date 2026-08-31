# -*- coding: utf-8 -*-
"""诊断：列出 b2/b5/b6 收件箱中来自 AGENT(b4) 的近期邮件（主题+日期），
判断 009 是否真的发了 G、发到了哪个邮箱、主题关键词是什么。"""
import imaplib
import os
import email as em
from datetime import datetime, timedelta

IMAP_HOST = os.getenv("SMOKE_IMAP_HOST", "127.0.0.1")
IMAP_PORT = int(os.getenv("SMOKE_IMAP_PORT", "1993"))
AGENT = "biquanzhi4@163.com"
ACCOUNTS = {
    "b2": ("biquanzhi2@163.com", os.environ.get("MI2_PASS", "")),
    "b5": ("biquanzhi5@163.com", os.environ.get("MI5_PASS", "")),
    "b6": ("biquanzhi6@163.com", os.environ.get("MI6_PASS", "")),
}


def _dec(s):
    if not s:
        return ""
    from email.header import decode_header
    try:
        return "".join(t.decode(e or "utf-8") if isinstance(t, bytes) else t for t, e in decode_header(s))
    except Exception:
        return str(s)


def list_from_agent(email, pw, since_min=60):
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(email, pw)
    imaplib.Commands["ID"] = ("AUTH",)
    try:
        imap._simple_command("ID", '("name" "CoTest" "vendor" "NeuOps")')
    except Exception:
        pass
    imap.select("INBOX")
    _, data = imap.search(None, "ALL")
    out = []
    cutoff = datetime.now() - timedelta(minutes=since_min)
    for num in reversed((data[0] or b"").split()):
        try:
            _, d = imap.fetch(num, "(RFC822)")
        except Exception:
            continue
        raw = d[0][1] if d and d[0] else None
        if not raw:
            continue
        m = em.message_from_bytes(raw)
        frm = _dec(m.get("From", ""))
        if AGENT.lower() not in frm.lower():
            continue
        subj = _dec(m.get("Subject", ""))
        date = m.get("Date", "")
        out.append((date, subj))
    imap.logout()
    return out


if __name__ == "__main__":
    for k, (email, pw) in ACCOUNTS.items():
        print(f"===== {k} ({email}) 来自 b4 的近 {60} 分钟邮件 =====", flush=True)
        try:
            for date, subj in list_from_agent(email, pw):
                print(f"   [{date}] {subj}", flush=True)
        except Exception as e:
            print(f"   [err] {e}", flush=True)
