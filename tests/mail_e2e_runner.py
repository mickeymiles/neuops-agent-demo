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
B5 = "biquanzhi5@163.com"; P5 = lambda: _pwd("5")  # 审批人

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
        try:
            typ, d = imap.fetch(num, "(BODY.PEEK[])")
        except Exception:
            continue
        if d and d[0]:
            raw = d[0][1] if isinstance(d[0], tuple) else d[0]
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

def send_mail(email, pw, to, subject, body, cc=None, reply_to=None, name=None):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((name or email, email))
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

def wait_tasks(pred, timeout=360, interval=15, label="?状态?"):
    """轮询 /tasks，直到有任务满足 pred(task)，返回该任务；超时返回 None。
    用于等待系统 tick 推进到目标内部/外部状态，替代固定的 sleep。
    """
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        d = api("/api/procurement-agent/mail-inquiry/tasks?page_size=20")
        for t in d.get("tasks", []):
            if pred(t):
                return t
        print(f"  … 等待{label}（还余{int(deadline-_t.time())}s）…")
        _t.sleep(interval)
    return None

def step_cfg():
    d = api("/api/procurement-agent/mail-inquiry/config?mask=false")
    c = d.get("credentials", {}); p = d.get("participants", {})
    print("采购方:", c.get("mail_username"), "| configured:", d.get("mail_configured"))
    print("审批人:", p.get("approver_emails"))
    print("供应商:", [(s.get("name"), s.get("email")) for s in p.get("default_suppliers", [])])

def step_sent():
    print("[工程师 b1 → 采购方 b3] 发送正式询价（必填字段齐全）")
    import time as _t
    seq = int(_t.time()) % 100000
    project_no = f"PRJ-E2E-{seq}"
    project_name = f"自动化E2E测试#{seq}"
    body = (
        f"您好，需要采购以下备件，请协助询价。\n\n"
        f"项目编号：{project_no}\n项目名称：{project_name}\n"
        "类型：硬盘\n品牌：Seagate\nPN：ST-E2E-200\n规格：1TB 7200转\n"
        "成色：全新\n数量：3\n"
        "收货地址：大连市高新园区测试路2号 王工 15900000001\n"
        "紧急程度：5min\n最晚发货时间：2026-09-12\n"
    )
    mid = send_mail(B1, P1(), B3, f"【备件询价】{project_no} 硬盘询价", body, name="运维工程师")
    print(f"  项目编号: {project_no}")
    print(f"  已发送: {mid}")

def step_sendbad():
    print("[工程师 b1 → 采购方 b3] 发送格式错误询价（缺品牌/PN/数量）")
    body = "您好，我需要采购备件，请尽快。\n类型：硬盘\n"
    mid = send_mail(B1, P1(), B3, "【备件询价】缺少关键字段", body, name="运维工程师")
    print(f"  已发送: {mid}")

def step_quote():
    print("[供应商 b2] 从服务器取最新 WAITING_QUOTES 任务供应商 B message_id，并从 b2 收件箱取 B 原询价构造带引用的标准报价回复")
    target = wait_tasks(lambda t: t.get("status") == "WAITING_QUOTES", label="WAITING_QUOTES任务")
    if not target:
        print("  ✗ 超时无 WAITING_QUOTES 任务")
        return
    tid = target["task_id"]
    try:
        suppliers = json.loads(target.get("suppliers_json") or "[]")
    except Exception:
        suppliers = []
    b_msg = None
    for s in suppliers:
        if (s.get("name") or s.get("email")) and (s.get("msg_id") or ""):
            b_msg = s["msg_id"]
            break
    if not b_msg:
        print("  ✗ 任务供应商无 B message_id:", suppliers)
        return
    print(f"  任务 {tid} 供应商 B message_id: {b_msg}")

    # 从 b2(供应商)收件箱取原询价 B 邮件正文，用于"全部回复"式引用
    import email as em
    orig_body = ""
    orig_subject = ""
    try:
        for raw in fetch_inbox(B2, P2(), limit=15):
            try:
                msg = em.message_from_bytes(raw)
                subj = _dec(msg.get("Subject", ""))
                mid2 = _dec(msg.get("Message-ID", ""))
                if mid2 and mid2.strip() == (b_msg or "").strip():
                    orig_subject = subj
                    # 提取纯文本正文
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                orig_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                                break
                    else:
                        orig_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='replace')
                    break
            except Exception:
                continue
    except Exception as e:
        print("  (取原询价引用失败，将仅发标准报价)", e)

    # 标准报价回复（依设计文档字段规范），并在下方引用原询价内容
    quote_lines = [
        "尊敬的采购方：",
        "您好！针对贵司询价，我方报价如下：\n",
        "备件品牌：Seagate",
        "型号（PN）：ST-E2E-200",
        "报价数量：3",
        "报价单价：1180元",
        "成色：全新",
        "交货周期：5天",
        "是否提供测试报告：是\n",
        "以上报价有效期即为贵司询价截止前，请查收确认。\n",
        "- 供应商A",
    ]
    reply = "\n".join(quote_lines)
    if orig_body:
        quoted = "\n".join(f"> {ln}" for ln in orig_body.splitlines())
        reply += f"\n\n在 {orig_subject or '询价'} 中写道：\n{quoted}"
    subj = f"Re: {orig_subject or '【询价】报价'}"
    mid = send_mail(B2, P2(), B3, subj, reply, reply_to=b_msg, name="供应商A")
    print(f"  供应商已按标准格式+带引用回复报价: {mid}")

def step_approve():
    print("[审批人 b5] 取服务器最新 R_APPROVAL 任务的 d_mail_msg_id → 在 D 线程上回复确认采购")
    target = wait_tasks(lambda t: t.get("internal_status") == "R_APPROVAL", label="R_APPROVAL任务")
    if not target:
        print("  ✗ 超时无 R_APPROVAL 任务")
        return
    tid = target["task_id"]
    d_mid = target.get("d_mail_msg_id") or ""
    if not d_mid:
        print("  ✗ 任务无 d_mail_msg_id")
        return
    print(f"  任务 {tid} d_mail_msg_id: {d_mid}")

    # 从 b5 收件箱取 D 邮件原文（全部回复式引用）
    import email as em
    orig_body = ""; orig_subject = "【询价汇总】"
    try:
        for raw in fetch_inbox(B5, P5(), limit=15):
            try:
                msg = em.message_from_bytes(raw)
                mid2 = _dec(msg.get("Message-ID", ""))
                if mid2 and mid2.strip() == d_mid.strip():
                    orig_subject = _dec(msg.get("Subject", ""))
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                orig_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                                break
                    else:
                        orig_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='replace')
                    break
            except Exception:
                continue
    except Exception as e:
        print("  (取 D 邮件原文失败，将仅发标准确认)", e)

    body = "确认采购，按最低价执行。\n\n- 审批人"
    if orig_body:
        quoted = "\n".join(f"> {ln}" for ln in orig_body.splitlines())
        body += f"\n\n在 {orig_subject} 中写道：\n{quoted}"

    mid = send_mail(B5, P5(), B3,
                    f"Re: {orig_subject}", body, reply_to=d_mid, name="采购审批人")
    print(f"  审批人 b5 已确认: {mid}")

def step_ship():
    """供应商 b2 在 E 订货邮件线程上回复快递单号（真实 SMTP + 引用原文）"""
    print("[供应商 b2] 取服务器最新 R_WAIT_SHIPPING 任务的 e_mail_msg_id → 在 E 线程上回快递单号")
    target = wait_tasks(lambda t: t.get("external_status") == "R_WAIT_SHIPPING", label="R_WAIT_SHIPPING任务")
    if not target:
        print("  ✗ 超时无 R_WAIT_SHIPPING 任务")
        return
    tid = target["task_id"]
    e_mid = target.get("e_mail_msg_id") or ""
    if not e_mid:
        print("  ✗ 任务无 e_mail_msg_id")
        return
    print(f"  任务 {tid} e_mail_msg_id: {e_mid[:60]}")

    # 从 b2 收件箱找 E 邮件原文（引用）
    import email as em
    orig_body = ""; orig_subject = "【订货确认】"
    try:
        for raw in fetch_inbox(B2, P2(), limit=15):
            try:
                msg = em.message_from_bytes(raw)
                mid2 = _dec(msg.get("Message-ID", ""))
                if mid2 and mid2.strip() == e_mid.strip():
                    orig_subject = _dec(msg.get("Subject", ""))
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                orig_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                                break
                    else:
                        orig_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='replace')
                    break
            except Exception:
                continue
    except Exception as ex:
        print("  (取 E 原文失败)", ex)

    body = "您好，订货已发出，快递单号：SF8822168990\n预计 3 天内到达，请查收。\n\n- 供应商A"
    if orig_body:
        quoted = "\n".join(f"> {ln}" for ln in orig_body.splitlines())
        body += f"\n\n在 {orig_subject} 中写道：\n{quoted}"

    mid = send_mail(B2, P2(), B3, f"Re: {orig_subject}", body, reply_to=e_mid, name="供应商A")
    print(f"  供应商已回单号: {mid}")

def step_done():
    """工程师 b1 在 D 汇总邮件线程上回复备件更换完成 → 触发 G 结算 → DONE"""
    print("[工程师 b1] 取服务器最新(已登记shipped_no)R_APPROVAL 任务的 d_mail_msg_id → 回复备件更换完成")
    target = wait_tasks(lambda t: t.get("internal_status") == "R_APPROVAL" and t.get("shipped_no"),
                        label="已收货待验收的R_APPROVAL任务")
    if not target:
        print("  ✗ 超时无已登记shipped_no的待验收任务")
        return
    d_mid = target.get("d_mail_msg_id") or target.get("thread_msg_id") or ""
    print(f"  任务 {target['task_id']} 用 reply_to={d_mid[:60]}")
    mid = send_mail(B1, P1(), B3, "Re: 【询价汇总】备件更换完成确认",
                    "备件已更换完成，可以结算了。\n\n- 运维部工程师",
                    reply_to=d_mid, name="运维工程师")
    print(f"  工程师已确认更换完成: {mid}")

def step_full():
    """跑全流程：sent → quote → approve → ship → done（各 step 内部轮询等待系统 tick 推进）"""
    print("=== 全流程自动执行 ===")
    step_sent()
    print("  … 等待首轮 tick 建任务并发询价 B …")
    step_quote(); step_approve()
    print("  … 等系统审批通过后发 E 订货邮件 …")
    step_ship()
    print("  … 等系统登记快递单号 …")
    step_done()
    print("\n=== 最终状态 ===")
    step_status()
    print("\n=== 各邮箱最近邮件 ===")
    step_check()

def step_status():
    d = api("/api/procurement-agent/mail-inquiry/tasks?page_size=20")
    for t in d.get("tasks", []):
        print(f"  {t.get('task_id')} | {t.get('status')} | ext={t.get('external_status')} | int={t.get('internal_status')} | shipped={t.get('shipped_no','-')} | step={t.get('latest_step','')[:80]}")

def step_check():
    for email, pw, name in ((B3, P3(), "采购方b3"), (B1, P1(), "工程师b1"), (B2, P2(), "供应商b2"), (B5, P5(), "审批人b5")):
        print(f"\n=== {name} ({email}) 收件箱最近邮件 ===")
        try:
            for m in raw_summaries(email, pw, limit=8):
                print(f"  - {m.get('subject','')[:60]} | from {m.get('from','')[:40]}")
        except Exception as e:
            print("  拉取失败:", e)

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "cfg"
    fn = {"cfg": step_cfg, "sent": step_sent, "sendbad": step_sendbad,
          "quote": step_quote, "approve": step_approve, "ship": step_ship,
          "done": step_done, "status": step_status, "check": step_check,
          "full": step_full}.get(step)
    if not fn:
        print("未知 step:", step); sys.exit(2)
    fn()