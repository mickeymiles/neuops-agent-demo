#!/usr/bin/env python3
"""Read recent emails from all 6 mailboxes to reconstruct the latest co-test trail."""
import os, sys, imaplib, ssl, email
from email.header import decode_header

BOXES = {
    "b1 张运维(发起人)": ("biquanzhi1@163.com", os.environ.get("MI1_PASS")),
    "b2 中软国际(供应商)": ("biquanzhi2@163.com", os.environ.get("MI2_PASS")),
    "b4 采购智能体(009)": ("biquanzhi4@163.com", os.environ.get("B4_PASS")),
    "b5 李审批(审批人)": ("biquanzhi5@163.com", os.environ.get("MI5_PASS")),
    "b6 神州数码(供应商)": ("biquanzhi6@163.com", os.environ.get("MI6_PASS")),
}
HOST, PORT = os.environ.get("SMOKE_IMAP_HOST", "imap.163.com"), int(os.environ.get("SMOKE_IMAP_PORT", "993"))

def _dec(v):
    if v is None: return ""
    out=[]
    for s,enc in decode_header(v):
        if isinstance(s,bytes): out.append(s.decode(enc or "utf-8","ignore"))
        else: out.append(s)
    return "".join(out)

def _date_ts(msg):
    from email.utils import parsedate_to_datetime
    dt = parsedate_to_datetime(msg.get("Date"))
    if dt is None: return None
    if dt.tzinfo is not None: dt = dt.astimezone().replace(tzinfo=None)
    return dt.timestamp()

def read(box):
    addr, pw = box
    if not pw: return []
    try:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        c = imaplib.IMAP4_SSL(HOST, PORT, ssl_context=ctx)
        c.login(addr, pw)
        c.select("INBOX")
        ok, data = c.search(None, "ALL")
        if ok != "OK": return []
        ids = data[0].split()
        out=[]
        for mid in ids[-40:]:
            ok, d = c.fetch(mid, "(RFC822)")
            if ok != "OK": continue
            m = email.message_from_bytes(d[0][1])
            out.append((_date_ts(m), _dec(m.get("From")), _dec(m.get("Subject")), mid.decode()))
        c.logout()
        return sorted(out, key=lambda x:(x[0] or 0))
    except Exception as e:
        return [("ERR", addr, str(e), "")]

if __name__=="__main__":
    for name, box in BOXES.items():
        print(f"\n===== {name} ({box[0]}) =====")
        rows = read(box)
        if not rows:
            print("  (空/无邮件)")
        for ts, frm, subj, mid in rows[-25:]:
            ts = f"{ts:.0f}" if isinstance(ts,(int,float)) else str(ts)
            print(f"  {ts} | {frm[:32]:32} | {subj[:60]}")
