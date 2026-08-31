# -*- coding: utf-8 -*-
"""本体轨 ont-emp009 真实邮箱端到端冒烟（本机 9007 + biquanzhi1~6@163.com）。

跑法（口令从环境变量读，勿硬编码进仓库）：
  MI1_PASS=xxx MI2_PASS=xxx MI5_PASS=xxx MI6_PASS=xxx \
  PYTHONPATH=. .venv/bin/python tests/ont_smoke_real.py

流程（上线测试·真实身份）：
  张运维(b1) →(A询价)→ 采购智能体(b4) →(B询价)→ 中软国际(b2)/神州数码(b6)
  中软国际/神州数码 →(报价)→ 采购智能体 →(D审批汇总)→ 李审批(b5)
  李审批 →(确认采购,沿用最低价)→ 采购智能体 →(E订货)→ 最低价供应商
  最低价供应商 →(快递单号)→ 采购智能体 → 登记完成

注：b1 后续会携带 2 个真实业务邮箱共同作为发起人（由用户稍后提供），
届时把对应邮箱+口令加入下方 REQUESTERS / 口令环境变量即可，脚本无需改动。
"""
import imaplib
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

IMAP_HOST, IMAP_PORT = "imap.163.com", 993
SMTP_HOST, SMTP_PORT = "smtp.163.com", 465
AGENT = "biquanzhi4@163.com"

B1 = "biquanzhi1@163.com"; P1 = os.environ.get("MI1_PASS", "")
B2 = "biquanzhi2@163.com"; P2 = os.environ.get("MI2_PASS", "")
B5 = "biquanzhi5@163.com"; P5 = os.environ.get("MI5_PASS", "")
B6 = "biquanzhi6@163.com"; P6 = os.environ.get("MI6_PASS", "")


def _dec(s):
    if not s:
        return ""
    try:
        return "".join(t.decode(e or "utf-8") if isinstance(t, bytes) else t for t, e in decode_header(s))
    except Exception:
        return str(s)


def _imap_find(email, pw, from_addr=None, contains=None, limit=40):
    """取收件箱最近 limit 封（ALL），在 Python 端按 from_addr/contains 过滤。
    避开 163 IMAP 的 SINCE/FROM 组合搜索坑。"""
    import email as em
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(email, pw)
    imaplib.Commands["ID"] = ("AUTH",)
    try:
        imap._simple_command("ID", '("name" "Smoke" "vendor" "NeuOps")')
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
        out.append((_dec(msg.get("Message-ID", "")), subj, _body_of(msg), raw))
        if len(out) >= limit:
            break
    imap.logout()
    return out[0] if out else None


def wait_for_inbox(email, pw, from_addr, timeout=45, label="邮件"):
    """轮询收件箱，直到出现来自 from_addr 的邮件（真实到达后才继续）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f = _imap_find(email, pw, from_addr=from_addr)
        if f:
            return f
        time.sleep(3)
    return None


def _body_of(msg):
    try:
        if msg.is_multipart():
            for p in msg.walk():
                if p.get_content_type() == "text/plain":
                    return p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return ""


def _smtp_send(email, pw, to, subject, body, reply_to=None, name=None):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((name or email, email))
    msg["To"] = to
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"] = reply_to
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.login(email, pw)
        s.sendmail(email, [to], msg.as_string())
    return str(msg["Message-ID"])


def agent_run(use_llm=False):
    from app.ontology import orbit, mail_gateway as mg
    return orbit.run_full(mg, use_llm=use_llm)


def get_ont_task(project_no):
    from app.ontology import store
    for t in store.list_tasks(limit=500):
        if t.get("mode") == "ontology" and (t.get("spare_info") or {}).get("project_no") == project_no:
            return t
    return None


def reset_old_tasks():
    """冒烟前把旧的非终态本体轨任务标记为终止，避免 run_full 把它们也驱动一遍。"""
    from app.ontology import store, orbit
    n = 0
    for t in store.list_tasks(limit=500):
        if t.get("mode") == "ontology" and t.get("status") not in orbit._TERMINAL:
            store.upsert_task({**t, "status": "CLOSED_ABORT", "external_status": "CLOSED_ABORT"})
            n += 1
    return n


def log(*a):
    print("[SMOKE]", *a, flush=True)


def main():
    missing = [n for n, p in (("MI1/b1", P1), ("MI2/b2", P2), ("MI5/b5", P5), ("MI6/b6", P6)) if not p]
    if missing:
        log("缺口令环境变量:", ", ".join(missing), "→ 退出")
        sys.exit(2)

    reset = reset_old_tasks()
    log(f"已清理旧非终态本体轨任务 {reset} 个")

    seq = int(time.time()) % 1000000
    pno = f"PRJ-ONT-{seq}"
    log(f"项目编号={pno}")

    # 1) 工程师 b1 → b4 发正式询价 A
    body = (
        f"您好，需要采购以下备件，请协助询价。\n\n"
        f"项目编号：{pno}\n项目名称：本体轨真实邮箱冒烟#{seq}\n"
        "类型：硬盘\n品牌：Seagate\nPN：ST-ONT-001\n规格：1TB 7200转\n"
        "成色：全新\n数量：2\n"
        "收货地址：大连市高新园区测试路2号 王工 15900000001\n"
        "紧急程度：48h\n最晚发货时间：2026-09-30\n"
    )
    _smtp_send(B1, P1, AGENT, f"【备件询价】{pno} 硬盘询价", body, name="张运维")
    log("① 已发询价 A (b1→b4)")

    # 2) 本体轨认领 + 发询价 B → b2/b6
    time.sleep(3)
    agent_run(use_llm=False)
    t = get_ont_task(pno)
    assert t, "任务未建"
    log("② 任务创建:", t["task_id"], "| 已发 B →", t["spare_info"].get("b_msg_ids"))
    # 真实到达校验：b2/b6 收件箱应真实收到来自 b4 的询价 B
    for sup, pw in ((B2, P2), (B6, P6)):
        got = wait_for_inbox(sup, pw, from_addr=AGENT, timeout=45)
        log(f"   真实到达校验 {sup}:", "✅ 收到b4邮件" if got else "⚠️ 未查到")

    # 3) b2/b6 回报价（b2 价高、b6 价低 → 最低价应选 b6）
    time.sleep(2)
    meta = t["spare_info"]
    suppliers = meta.get("suppliers") or []
    b_mids = meta.get("b_msg_ids") or []
    price_by = {B2: "1280", B6: "980"}
    assert len(suppliers) == len(b_mids) >= 2, "b_msg_ids 与供应商数量不匹配"
    SUP_NAME = {B2: "中软国际", B6: "神州数码"}
    for sup, bmid in zip(suppliers, b_mids):
        email = sup["email"]
        pw = P2 if email == B2 else P6
        price = price_by.get(email, "1000")
        found = wait_for_inbox(email, pw, from_addr=AGENT, timeout=45)
        assert found, f"{email} 未收到询价 B（真实邮件未到达）"
        mid, subj, _, _ = found
        quote = (f"尊敬采购方：\n针对贵司询价，我方报价如下：\n"
                 f"品牌：Seagate\n型号：ST-ONT-001\n数量：2\n单价：{price}元\n"
                 f"成色：全新\n货期：5天\n- {SUP_NAME.get(email, '供应商')}")
        _smtp_send(email, pw, AGENT, f"Re: {subj}", quote, reply_to=mid,
                   name=SUP_NAME.get(email, "供应商"))
        log(f"③ {email}（{SUP_NAME.get(email, '供应商')}）已回报价 {price}元 (reply→{mid[:24]}…)")
    t = get_ont_task(pno)

    # 4) 归集报价 + 发审批 D → b5
    time.sleep(3)
    agent_run(use_llm=False)
    t = get_ont_task(pno)
    quotes = (t["spare_info"].get("quotes") or [])
    log("④ 已收报价数:", len(quotes),
        "| 智能体固定选最低价(agent_selected):", t["spare_info"].get("agent_selected_supplier"))
    assert len(quotes) == 2, "应收到 2 份报价"
    assert t["spare_info"].get("agent_selected_supplier") == B6, "最低价应为 b6"

    # 5) b5 审批「确认采购」（应沿用最低价 b6，不点名）
    time.sleep(2)
    dfound = wait_for_inbox(B5, P5, from_addr=AGENT, timeout=45)
    assert dfound, "b5 未收到审批 D（真实邮件未到达）"
    dmid, dsubj, _, _ = dfound
    _smtp_send(B5, P5, AGENT, f"Re: {dsubj}",
               "确认采购，按比价最低价执行。\n- 李审批", reply_to=dmid, name="李审批")
    log("⑤ b5 已回复「确认采购」 (reply→" + dmid[:24] + "…)")

    # 6) 归集审批 + 发订货 E → 最低价供应商
    time.sleep(3)
    agent_run(use_llm=False)
    t = get_ont_task(pno)
    log("⑥ 审批后 target_supplier:", t["spare_info"].get("target_supplier"),
        "| external:", t["external_status"])

    # 7) 最低价供应商(b6) 回快递单号
    time.sleep(2)
    efound = wait_for_inbox(B6, P6, from_addr=AGENT, timeout=45)
    assert efound, "b6 未收到订货 E（真实邮件未到达）"
    emid, esubj, _, _ = efound
    _smtp_send(B6, P6, AGENT, f"Re: {esubj}",
               "订货已发出，快递单号：SF8882001ONT\n预计3天到达。\n- 神州数码", reply_to=emid, name="神州数码")
    log("⑦ b6 已回快递单号 (reply→" + emid[:24] + "…)")

    # 8) 归集单号
    time.sleep(3)
    agent_run(use_llm=False)
    t = get_ont_task(pno)
    log("⑧ 最终 external_status:", t["external_status"],
        "| tracking:", (t["spare_info"] or {}).get("tracking_no", "-"))

    assert t["spare_info"].get("target_supplier") == B6, "下单供应商应为最低价 b6"
    log("✅ 真实邮箱冒烟全流程跑通。任务", t["task_id"],
        "| 状态", t["external_status"], "| 下单", t["spare_info"].get("target_supplier"))


if __name__ == "__main__":
    main()
