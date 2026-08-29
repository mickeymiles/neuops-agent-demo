# -*- coding: utf-8 -*-
"""
备件邮件询价 真邮箱端到端测试驱动（针对服务器 122.51.98.98:9007）

角色分工：
  - 采购方/系统：biquanzhi3@163.com（服务器 proc_credentials）
  - 工程师：biquanzhi1@163.com
  - 供应商：biquanzhi2@163.com（临时兼任审批人，审批白名单设 biquanzhi1@163.com）

用法（凭据从环境变量读，勿硬编码）：
  MI1_PASS=xxx MI2_PASS=xxx MI3_PASS=xxx python3 tests/mail_e2e_runner.py <step>

  <step>:
    cfg     打印/校验服务器配置
    sent    (工程师b1)发询价A到 b3   [必填字段齐全]         → 等自动tick → b3应收B
    sendbad (工程师b1)发格式错误询价到 b3                    → 应收到回信提示，不建任务
    quote   (供应商b2)读到b3最新B→reply报价到b3              → 汇总/审批
    approve (工程师b1)读到b3最新D→reply“确认采购”到b3        → 订货
    status  打印服务器任务列表
    check   打印各邮箱收件箱最近邮件标题

服务器 tick 每 2 分钟自动触发一次（main.py _proc_scheduler_loop）。
"""
import imaplib
import json
import os
import smtplib
import sys
import time
from datetime import datetime
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

SERVER = "http://122.51.98.98:9007"

def _pwd(suffix):
    v = os.environ.get(f"MI{suffix}_PASS", "")
    if not v:
        print(f"[缺凭据] 请设 MI{suffix}_PASS 环境变量"); sys.exit(2)
    return v

B1 = "biquanzhi1@163.com"; P1 = lambda: _pwd("1")
B2 = "biquanzhi2@163.com"; P2 = lambda: _pwd("2")
B3 = "biquanzhi3@163.com"; P3 = lambda: _pwd("3")

IMAP_HOST, IMAP_PORT = "imap.163.com", 993
SMTP_HOST, SMTP_PORT = "smtp.163.com", 465

def _dec(s):
    if not s: return ""
    parts = decode_header(s); out = []
    for t, enc in parts:
        out.append(t.decode(enc or "utf-8") if isinstance(t, bytes) else t)
    return "".join(out)

def fetch_inbox(email, pw, limit=15, since_days=2):
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(email, pw)
    imaplib.Commands["ID"] = ("AUTH",)
    try: imap._simple_command("ID", '("name" "E2E" "vendor" "Run")')
    except Exception: pass
    imap.select("INBOX")
    t = datetime.now().strftime("%d-%b-%Y")
    _, data = imap.search(None, f'SINCE {t}')
    mails = []
    for num in reversed((data[0] or b"").split()):
        _, d = imap.fetch(num, "(BODY[] .)")
        raw = d[0][1] if d and d[0] else b""
        mails.append(raw)
        if len(mails) >= limit: break
    imap.logout()
    return mails

def raw_summaries(email, pw, limit=10):
    """返回最近的原始邮件头摘要列表。"""
    raws = fetch_inbox(email, pw, limit=limit)
    out = []
    import email as em
    for raw in raws:
        try:
            msg = em.message_from_bytes(raw)
            subj = _dec(msg.get("Subject", ""))
            frm = _dec(msg.get("From", ""))
            mid = _dec(msg.get("Message-ID", ""))
            to = _dec(msg.get("To", ""))
            irt = _dec(msg.get("In-Reply-To", ""))[:40]
            out.append({"subject": subj, "from": frm, "to": to, "message_id": mid, "in_reply_to": irt, "raw": raw})
        except Exception as e:
            out.append({"error": str(e)})
    return out

def send_mail(email, pw, to, subject, body, cc=None, reply_to=None):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("E2E", email))
    msg["To"] = to if isinstance(to, str) else ",".join(to)
    msg["Message-ID"] = make_msgid()
    if cc: msg["Cc"] = cc if isinstance(cc, str) else ",".join(cc)
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"] = reply_to
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(email, pw)
        s.sendmail(email, [to] if isinstance(to, str) else list(to) + (list(cc or [])), msg.as_string())
    return str(msg["Message-ID"])

def api(path, meth="GET", body=None):
    import urllib.request
    req = urllib.request.Request(SERVER + path, method=meth)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"success": False, "err": str(e)}

def wait_tick(seconds=20):
    print(f"  … 等待服务器自动 tick（{seconds}s）…")
    time.sleep(seconds)

def step_cfg():
    d = api("/api/procurement-agent/mail-inquiry/config?mask=false")
    c = d.get("credentials", {}); p = d.get("participants", {})
    print("采购方:", c.get("mail_username"), "| configured:", d.get("mail_configured"))
    print("审批人:", p.get("approver_emails"))
    print("供应商:", [(s.get("name"), s.get("email")) for s in p.get("default_suppliers", [])])

def step_sent():
    print("[工程师 b1 → 采购方 b3] 发送询价 A（字段齐全）")
    body = (
        "您好，我是运维部工程师，现发起备件询价申请。\n\n"
        "项目编号：PRJ-E2E-001\n项目名称：真邮箱端到端测试\n"
        "类型：硬盘\n品牌：Seagate\nPN：ST-E2E-100\n规格：1TB 7200转\n"
        "成色：全新\n数量：4\n"
        "收货地址：大连市高新园区测试路1号 李工 15900000000\n"
        "询价时间：一天\n最晚发货时间：2026-09-10\n"
    )
    mid = send_mail(B1, P1(), B3, "【备件询价】PRJ-E2E-001 硬盘询价", body)
    print(f"  已发送: {mid}")

def step_sendbad():
    print("[工程师 b1 → 采购方 b3] 发送格式错误询价（缺品牌/PN/数量）")
    body = "您好，我需要采购备件，请尽快。\n类型：硬盘\n"
    mid = send_mail(B1, P1(), B3, "【备件询价】缺少关键字段", body)
    print(f"  已发送: {mid}")

def step_quote():
    print("[供应商 b2] 读取采购方 b3 收件箱中的 B 询价邮件（含 message_id）")
    mails = raw_summaries(B3, P3(), limit=20)
    b = None
    for m in mails:
        if "【询价】" in m.get("subject", "") and not b:
            b = m
    if not b:
        print("  ✗ 未找到 B 询价邮件（可能 tick 未处理或失败）")
        for m in mails: print("    -", m.get("subject", "")[:60])
        return
    print("  找到 B:", b["subject"])
    print(f"  B message_id: {b['message_id']}")
    # 从 B 的 To 找供应商邮箱（应含 b2）
    reply = (
        "您好，贵司询价如下，我方报价：\n"
        "单价：1180元\n成色：全新\n数量：4\n发货时间：5天\n可提供测试报告：是\n"
    )
    mid = send_mail(B2, P2(), B3, "Re: " + b["subject"], reply, reply_to=b["message_id"])
    print(f"  供应商已回复报价: {mid}")

def step_approve():
    print("[审批人 b1] 读取采购方 b3 收件箱中的 D 汇总邮件 → 回复确认采购")
    mails = raw_summaries(B3, P3(), limit=20)
    d_mail = None
    for m in mails:
        if "【询价汇总】" in m.get("subject", "") and not d_mail:
            d_mail = m
    if not d_mail:
        print("  ✗ 未找到 D 汇总邮件（可能未到审批阶段）")
        for m in mails: print("    -", m.get("subject", "")[:60])
        return
    print("  找到 D:", d_mail["subject"])
    mid = send_mail(B1, P1(), B3, "Re: " + d_mail["subject"], "确认采购，按最低价执行。", reply_to=d_mail["message_id"])
    print(f"  审批人已确认: {mid}")

def step_status():
    d = api("/api/procurement-agent/mail-inquiry/tasks?page_size=20")
    for t in d.get("tasks", []):
        print(f"  {t.get('task_id')} | {t.get('status')} | {t.get('latest_step')} | 最低={t.get('lowest_supplier')}@{t.get('lowest_quote')}")

def step_check():
    for email, pw, name in ((B3, P3, "采购方b3"), (B1, P1, "工程师b1"), (B2, P2, "供应商b2")):
        print(f"\n=== {name} ({email}) 收件箱最近邮件 ===")
        try:
            for m in raw_summaries(email, pw, limit=8):
                print(f"  - {m.get('subject','')[:60]} | from {m.get('from','')[:40]}")
        except Exception as e:
            print("  拉取失败:", e)

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "cfg"
    fn = {"cfg": step_cfg, "sent": step_sent, "sendbad": step_sendbad,
          "quote": step_quote, "approve": step_approve, "status": step_status,
          "check": step_check}.get(step)
    if not fn:
        print("未知 step:", step); sys.exit(2)
    fn()