# -*- coding: utf-8 -*-
"""本地角色驱动器（分布式联调）：服务器 009 是 b4 邮箱主脑，本地只模拟 b1/b2/b5/b6 的邮件收发。

架构（与 ont_smoke_real.py 的区别）：
- 本脚本【绝不】本地运行本体轨 agent；所有决策/发信都由服务器 122.51.98.98:9007 上的 009 数字员工完成。
- 本地职责：
    * b1(工程师) → b4 发询价 A
    * 监听 b2/b6 收件箱：待服务器 009 发来询价 B 后，回报价
    * 监听 b5 收件箱：待服务器 009 发来审批 D 后，回「确认采购」
    * 监听 b6 收件箱：待服务器 009 发来订货 E 后，回快递单号
    * b1 → b4 发「更换完成」→ 触发服务器 009 发结算 G
    * （可选）读取 b4 收件箱做只读观察，确认 009 收发正常
- 服务器 009 调度间隔约 60s，故每步等待以 150s 为上限轮询真实邮件到达。

网络：本机直连 163 需经 HTTP 代理 CONNECT 白名单，故通常要另开 tools/proxy_mail_tunnel.py
      监听 127.0.0.1:1993/1465，并以 SMOKE_IMAP_HOST/PORT、SMOKE_SMTP_HOST/PORT 指向隧道。

口令（从环境变量读，勿硬编码）：
  MI1_PASS / MI2_PASS / MI5_PASS / MI6_PASS   # b1/b2/b5/b6 发送所需
  B4_PASS（可选，用于只读观察 b4 收件箱）      # 默认取已知 b4 口令
"""
import imaplib
import os
import re
import smtplib
import sys
import time
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

IMAP_HOST = os.getenv("SMOKE_IMAP_HOST", "imap.163.com")
IMAP_PORT = int(os.getenv("SMOKE_IMAP_PORT", "993"))
SMTP_HOST = os.getenv("SMOKE_SMTP_HOST", "smtp.163.com")
SMTP_PORT = int(os.getenv("SMOKE_SMTP_PORT", "465"))

AGENT = os.getenv("SMOKE_AGENT", "biquanzhi4@163.com")          # b4（服务器 009 控制）
B1 = os.getenv("SMOKE_B1", "biquanzhi1@163.com")
B2 = os.getenv("SMOKE_B2", "biquanzhi2@163.com")
B5 = os.getenv("SMOKE_B5", "biquanzhi5@163.com")
B6 = os.getenv("SMOKE_B6", "biquanzhi6@163.com")

P1 = os.environ.get("MI1_PASS", "")
P2 = os.environ.get("MI2_PASS", "")
P5 = os.environ.get("MI5_PASS", "")
P6 = os.environ.get("MI6_PASS", "")
# b4 口令仅用于只读观察其收件箱；缺省用已知值（测试账号）。
B4P = os.environ.get("B4_PASS", "GMydirfgUNnpp87F")

NAME = {B1: "张运维", B2: "中软国际", B5: "李审批", B6: "神州数码"}
SUP_NAME = {B2: "中软国际", B6: "神州数码"}

# 服务器 009 调度间隔约 60s，留足余量
WAIT = int(os.getenv("CO_WAIT", "150"))


def _dec(s):
    if not s:
        return ""
    try:
        return "".join(t.decode(e or "utf-8") if isinstance(t, bytes) else t for t, e in decode_header(s))
    except Exception:
        return str(s)


def _body_of(msg):
    try:
        if msg.is_multipart():
            for p in msg.walk():
                if p.get_content_type() == "text/plain":
                    return p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return ""


def _date_ts(msg):
    """解析邮件 Date 头为 epoch 秒；解析失败返回 None。"""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(msg.get("Date"))
        if dt is None:
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.timestamp()
    except Exception:
        return None


def _imap_find(email, pw, from_addr=None, contains=None, limit=40, after_ts=None):
    import email as em
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
    for num in reversed((data[0] or b"").split()):
        try:
            _, d = imap.fetch(num, "(RFC822)")
        except Exception:
            continue
        raw = d[0][1] if d and d[0] else None
        if not raw:
            continue
        msg = em.message_from_bytes(raw)
        frm = _dec(msg.get("From", ""))
        subj = _dec(msg.get("Subject", ""))
        if from_addr and from_addr.lower() not in frm.lower():
            continue
        if contains and contains not in subj and contains not in _body_of(msg):
            continue
        # 防跨任务污染：只认 A 发出之后、由服务器 009 新发的邮件
        if after_ts is not None:
            ts = _date_ts(msg)
            if ts is not None and ts < after_ts - 120:
                continue
        out.append((_dec(msg.get("Message-ID", "")), subj, _body_of(msg), raw, _dec(msg.get("Cc", ""))))
        if len(out) >= limit:
            break
    imap.logout()
    return out[0] if out else None


def wait_for_inbox(email, pw, from_addr, timeout=WAIT, label="邮件", contains=None, after_ts=None):
    """轮询收件箱，直到收到来自 from_addr 且（可选）正文/主题含 contains 的邮件。
    after_ts：仅认该时间戳（A 发出时刻）之后到达的邮件，避免误抓历史/陈旧任务的邮件。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f = _imap_find(email, pw, from_addr=from_addr, contains=contains, after_ts=after_ts)
        if f:
            return f
        time.sleep(5)
    return None


def task_no_of(subj):
    """从主题 [OT-xxxx] 中抽取任务号，用于过滤同一项目的 D/E/G 邮件。"""
    m = re.search(r"\[(OT-[\w]+)\]", subj or "")
    return m.group(1) if m else ""


# 运维工程师在初始询价 A 中抄送的观察者；智能体后续所有邮件都应携带这些人
EXPECT_CC = [B5, "biqzh@neusoft.com", "260110550@qq.com"]


def _cc_has(cc_raw, *addrs):
    """检查某封邮件的 Cc 头是否包含全部给定邮箱（大小写不敏感）。"""
    cc = (cc_raw or "").lower()
    return all(a.lower().strip() in cc for a in addrs)


def _smtp_send(email, pw, to, subject, body, reply_to=None, name=None, cc=None):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((name or email, email))
    msg["To"] = to
    if cc:
        msg["Cc"] = ",".join(cc)
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"] = reply_to
    rcpts = [to] + (list(cc) if cc else [])
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.login(email, pw)
        s.sendmail(email, rcpts, msg.as_string())
    return str(msg["Message-ID"])


def observe_b4(pno):
    """只读观察 b4 收件箱：列出与本项目相关的往来邮件（从 b1/b2/b5/b6 发来的、及 009 发出的痕迹）。"""
    if not B4P:
        print("[OBS] 未提供 B4_PASS，跳过 b4 收件箱只读观察。", flush=True)
        return
    try:
        f = _imap_find(AGENT, B4P, contains=pno, limit=60)
        print("[OBS] b4 收件箱（项目相关，最近若干封）：", flush=True)
        # 列出所有含项目号的邮件主题
        import email as em
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(AGENT, B4P)
        imaplib.Commands["ID"] = ("AUTH",)
        try:
            imap._simple_command("ID", '("name" "CoTest" "vendor" "NeuOps")')
        except Exception:
            pass
        imap.select("INBOX")
        _, data = imap.search(None, "ALL")
        n = 0
        for num in reversed((data[0] or b"").split()):
            try:
                _, d = imap.fetch(num, "(RFC822)")
            except Exception:
                continue
            raw = d[0][1] if d and d[0] else None
            if not raw:
                continue
            m = em.message_from_bytes(raw)
            subj = _dec(m.get("Subject", ""))
            frm = _dec(m.get("From", ""))
            if pno in subj or pno in _body_of(m):
                print(f"      - 来自 {frm[:40]} | 主题 {subj[:60]}", flush=True)
                n += 1
            if n >= 30:
                break
        imap.logout()
    except Exception as e:
        print(f"[OBS] b4 只读观察失败：{e}", flush=True)


def log(*a):
    print("[CO-TEST]", *a, flush=True)


def main():
    missing = [n for n, p in (("MI1/b1", P1), ("MI2/b2", P2), ("MI5/b5", P5), ("MI6/b6", P6)) if not p]
    if missing:
        log("缺口令环境变量:", ", ".join(missing), "→ 退出（本驱动器本地只发邮件，需要这些口令）")
        sys.exit(2)

    seq = int(time.time()) % 1000000
    pno = f"PRJ-ONT-{seq}"
    log(f"项目编号={pno}；agent=b4={AGENT}（由服务器 009 控制）；本地模拟 b1/b2/b5/b6")

    # ① b1 → b4 正式询价 A（含 9 必填字段，避免触发 requestMissingFields）
    body = (
        f"您好，需要采购以下备件，请协助询价。\n\n"
        f"项目编号：{pno}\n项目名称：分布式联调真实邮箱测试#{seq}\n"
        "类型：硬盘\n品牌：Seagate\n型号：ST-ONT-001\n规格：1TB 7200转\n"
        "成色：全新\n数量：2\n"
        "收货地址：大连市高新园区测试路2号 王工 15900000001\n"
        "紧急程度：48h\n最晚发货时间：2026-09-30\n"
    )
    _smtp_send(B1, P1, AGENT, f"【备件询价】{pno} 硬盘询价", body,
               name=NAME[B1], cc=EXPECT_CC)
    a_sent_ts = time.time()
    log("① 已发询价 A (b1→b4)，等待服务器 009 认领并给 b2/b6 发询价 B…")

    # ② 服务器 009 发 B → b2/b6；本地回报价
    # B 主题不含项目号，用「发件人=009 + 关键词【询价】+ A 发出之后」过滤，防历史/陈旧任务误匹配
    b2m = wait_for_inbox(B2, P2, from_addr=AGENT, contains="【询价】", after_ts=a_sent_ts, label="b2 的 B")
    b6m = wait_for_inbox(B6, P6, from_addr=AGENT, contains="【询价】", after_ts=a_sent_ts, label="b6 的 B")
    assert b2m and b6m, "b2/b6 未在时限内收到服务器 009 发出的询价 B（检查 009 是否在轮询 b4）"
    task_no = task_no_of(b2m[1]) or task_no_of(b6m[1])
    assert task_no, f"无法从 B 主题解析 task_no：b2='{b2m[1]}' b6='{b6m[1]}'"
    log(f"② 服务器 009 已向 b2/b6 发出询价 B ✅（task_no={task_no}）")
    # 抄送透传断言：B 的 Cc 须含初始询价 A 的全部抄送观察者
    for who, bm in (("b2", b2m), ("b6", b6m)):
        assert _cc_has(bm[4], *EXPECT_CC), f"{who} 收到的 B 未携带全部抄送观察者：Cc={bm[4]!r}"
    log("② B 已携带抄送观察者(CC) ✅")
    price_by = {B2: "1280", B6: "980"}
    for sup, found in ((B2, b2m), (B6, b6m)):
        mid, subj, _, _, _ = found
        price = price_by.get(sup, "1000")
        quote = (f"尊敬采购方：\n针对贵司询价，我方报价如下：\n"
                 f"品牌：Seagate\n型号：ST-ONT-001\n数量：2\n单价：{price}元\n"
                 f"成色：全新\n货期：5天\n- {SUP_NAME.get(sup, '供应商')}")
        _smtp_send(sup, (P2 if sup == B2 else P6), AGENT, f"Re: {subj}", quote,
                   reply_to=mid, name=SUP_NAME.get(sup, "供应商"))
        log(f"   ③ {sup}（{SUP_NAME.get(sup)}）已回报价 {price}元")
    log("③ 报价已回，等待服务器 009 归集并给 b5 发审批 D…")

    # ④ 服务器 009 发 D → b5；b5 确认
    #   D 主题含「【询价汇总】」精确匹配；不能只用 task_no（E/G 也含 task_no，会误抓）。
    dfound = wait_for_inbox(B5, P5, from_addr=AGENT, contains="【询价汇总】",
                            after_ts=a_sent_ts, label="b5 的 D")
    assert dfound, f"b5 未在时限内收到服务器 009 发出的审批 D（task_no={task_no}）"
    dmid, dsubj, _, _, dcc = dfound
    assert "【询价汇总】" in dsubj, f"b5 收到的并非审批 D：{dsubj}"
    # 抄送透传断言：D 的 Cc 须含全部抄送观察者
    assert _cc_has(dcc, *EXPECT_CC), f"D 未携带全部抄送观察者：Cc={dcc!r}"
    log("④ 服务器 009 已向 b5 发出审批 D ✅（已携带抄送观察者）；b5 回复「确认采购」…")
    _smtp_send(B5, P5, AGENT, f"Re: {dsubj}", "确认采购，按比价最低价执行。\n- 李审批",
               reply_to=dmid, name=NAME[B5])
    log("⑤ b5 已回复「确认采购」，等待服务器 009 向最低价供应商发订货 E…")

    # ⑥ 服务器 009 发 E → 最低价供应商(b6)；b6 回单号
    #   ⚠️ 关键：必须用 E 专属主题「【订货确认】」精确匹配，不能只用 task_no
    #   （B 询价邮件也含 task_no）。若误抓 B，则「回单号」会线程挂到询价邮件上 →
    #   供应商在订单发出前就「发货」，后续 E 不再发出、G 无法触发（上一轮的根因）。
    #   这里会一直【等待订单邮件】到达后才允许 b6 回复单号，严格按流程顺序。
    efound = wait_for_inbox(B6, P6, from_addr=AGENT, contains="【订货确认】",
                            after_ts=a_sent_ts, label="b6 的 E（订货确认）")
    assert efound, f"b6 未在时限内收到服务器 009 发出的订货 E（task_no={task_no}）"
    emid, esubj, _, _, ecc = efound
    assert "【订货确认】" in esubj, f"b6 收到的并非订货 E：{esubj}"
    # 抄送透传断言：E 的 Cc 须含全部抄送观察者
    assert _cc_has(ecc, *EXPECT_CC), f"E 未携带全部抄送观察者：Cc={ecc!r}"
    log("⑥ 服务器 009 已向最低价供应商(b6)发出订货 E ✅（已携带抄送观察者）；b6 回快递单号…")
    _smtp_send(B6, P6, AGENT, f"Re: {esubj}", "订货已发出，快递单号：SF8882001ONT\n预计3天到达。\n- 神州数码",
               reply_to=emid, name=NAME[B6])
    log("⑦ b6 已回快递单号（线程挂在 E 上），等待工程师 b1 发「更换完成」触发结算 G…")

    # ⑧ b1 → b4 发「更换完成」：
    #   必须带 In-Reply-To=E 的 message-id（emid），否则 009 的 _thread_match(inrep, _mids_of)
    #   因无线程归属而忽略该邮件 → engineer_close 永不置位 → G 永不触发。
    time.sleep(3)
    _smtp_send(B1, P1, AGENT, f"Re: {esubj} 更换完成",
               "设备已更换完成，备件运行正常，请安排结算。\n- 张运维",
               reply_to=emid, name=NAME[B1])
    log("⑧ 已发「更换完成」(b1→b4，回复 E 线程 emid)，等待服务器 009 发结算 G…")

    # ⑨ 服务器 009 发 G → b6（结算）。
    #   G 主题含「【采购结束】」，精确匹配；E 主题为「【订货确认】」，不会误命中。
    gfound = wait_for_inbox(B6, P6, from_addr=AGENT, contains="【采购结束】",
                            after_ts=a_sent_ts, label="b6 的 G")
    assert gfound, f"b6 未在时限内收到服务器 009 发出的结算 G（task_no={task_no}）"
    gmid, gsubj, _, _, gcc = gfound
    # 抄送透传断言：G 的 Cc 须含全部抄送观察者
    assert _cc_has(gcc, *EXPECT_CC), f"G 未携带全部抄送观察者：Cc={gcc!r}"
    log("⑨ 服务器 009 已发出结算 G ✅（已携带抄送观察者）—— 全链路 B→D→E→F→G 在『服务器 agent + 本地角色』架构下跑通")

    # 只读观察 b4 收件箱
    observe_b4(pno)
    log(f"✅ 分布式联调完成。项目 {pno}：b4 收发由服务器 009 完成，本地仅模拟 b1/b2/b5/b6。")


if __name__ == "__main__":
    main()
