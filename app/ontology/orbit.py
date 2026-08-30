# -*- coding: utf-8 -*-
"""本体轨自走编排：SEEN 认领 + 入向回复归集 + 决策与执行（阶段 B/C）。
只有 Governor 放行（ontology/split + exec）才真正驱动；否则仅诊断。
状态与数据全部落在 O_*（独立于现轨 spare_mail_task）。
"""
import os
import re
import time

from . import store, execution
from .decision import build_fact_context

_TERMINAL = ("CLOSED_ABORT", "CLOSED_MANUAL", "R_SETTLE")
_APPROVE_KW = ("确认", "采购", "同意", "采纳", "就选")
_CLOSE_KW = ("完成", "测试完毕", "更换完成", "采购结束")
_SHIP_KW = ("单号", "快递单号", "物流单号", "运单")


def config():
    """读现轨参与者配置（只读）：默认供应商 + 审批人。
    DB `proc_participants`（审批人/供应商）优先，缺失回退 skill JSON；凭据只做 mail 兜底。"""
    suppliers, approvers = [], []
    try:
        from app.db.spare_mail import spare_mail_get_config
        p = spare_mail_get_config("proc_participants") or {}
        for s in (p.get("default_suppliers") or []):
            if isinstance(s, dict) and s.get("email"):
                suppliers.append({"name": s.get("name", ""), "email": s.get("email")})
        approvers = [e for e in (p.get("approver_emails") or []) if e]
    except Exception:
        p = {}
    # 兜底：skill JSON
    if not suppliers or not approvers:
        try:
            from app.utils import load_skill
            sk = load_skill("skill-proc-mail-inquiry") or {}
            comp = (sk.get("compose") or {}).get("participants") or (sk.get("participants") or {})
            if not suppliers:
                suppliers = [s for s in (comp.get("default_suppliers") or [])
                             if isinstance(s, dict) and s.get("email")]
            if not approvers:
                approvers = [e for e in (comp.get("approver_emails") or []) if e]
        except Exception:
            pass
    return {"suppliers": suppliers, "approvers": approvers}


def _mids_of(task):
    meta = task.get("spare_info") or {}
    mids = [(task.get("threat_msg_id") or "").strip()]
    mids += [m for m in (meta.get("b_msg_ids") or []) if m]
    for k in ("d_msg_id", "e_msg_id"):
        if meta.get(k):
            mids.append(meta[k])
    return {m.strip() for m in mids if m and m.strip()}


def _price(body):
    m = re.search(r"(?:单价|价格|报价)[：:\s]*([0-9]+(?:\.[0-9]+)?)", body)
    return m.group(1) if m else ""


def ctx_from_task(task):
    meta = task.get("spare_info") or {}
    quotes = meta.get("quotes") or []
    approvers = meta.get("approver_emails") or []
    target_list = meta.get("suppliers") or config()["suppliers"]
    valid = [q for q in quotes if q.get("email")]
    lowest = min(valid, key=lambda q: float(q.get("unit_price") or 10 ** 12)) if valid else None
    deadline_passed = meta.get("deadline_passed", False)
    # 下单供应商仅由审批人确认回复显式选定；未审批前不自动选最低价
    target_supplier = meta.get("target_supplier") or ""
    lowest_email = lowest["email"] if (valid and lowest) else ""
    internal = "R_CLOSED" if meta.get("engineer_close") else task.get("internal_status")
    ctx = {
        "project_no": meta.get("project_no"), "project_name": meta.get("project_name"),
        "part_type": meta.get("part_type"), "brand": meta.get("brand"), "pn": meta.get("pn"),
        "spec": meta.get("spec"), "condition": meta.get("condition"), "count": meta.get("count"),
        "address": meta.get("address"), "urgent": meta.get("urgent"),
        "from_email": task.get("from_email"), "approver_emails": approvers,
        "internal_status": internal, "external_status": task.get("external_status"),
        "target_supplier_list": [s.get("email") for s in target_list],
        "valid_quotes": valid, "valid_quote_count": len(valid), "raw_quote_count": len(quotes),
        "valid_supplier_emails": [q.get("email") for q in valid],
        "target_supplier": target_supplier,
        "lowest_supplier": lowest_email,
        "approval_choice": target_supplier,
        "tracking_number_candidate": meta.get("tracking_no", ""),
        "collection_done": bool(deadline_passed or (valid and len(quotes) >= len(target_list) and target_list)),
        "deadline_passed": bool(deadline_passed),
    }
    return ctx


# ── SEEN 认领：新工程师发起邮件 → 归本体轨并标记已读 ──────────────
def claim_inquiries(mg, mode="off", roll=0.0):
    claimed = []
    if mode not in ("ontology", "split"):
        return claimed
    try:
        from .ingest import fetch_new_inquiry_facts
        facts = fetch_new_inquiry_facts(mg, hours=48, store=store)
    except Exception as e:
        return claimed
    for it in facts:
        fields = it["fields"]
        fid = fields.get("message_id") or ""
        # split：按消息指纹滚
        if mode == "split":
            import hashlib
            h = int(hashlib.sha256(fid.encode()).hexdigest(), 16) % 1000 / 1000.0
            if h > roll:
                continue
        tid = f"OT-{_shake(fid)}"
        mail = it.get("mail") or {}
        into = {**fields, "suppliers": config()["suppliers"],
                "approver_emails": config()["approvers"],
                "quotes": [], "received_reply_ids": []}
        # 携带工程师原始采购申请（A）原文与线程元数据：供 D/F 回复同一线程并携带原文
        into["inquiry_raw"] = (fields.get("mail_body") or fields.get("body")
                               or mail.get("mail_body_text") or mail.get("body") or "")
        into["inquiry_mid"] = fid
        into["inquiry_refs"] = (mail.get("references") or "").strip()
        into["inquiry_reply_from"] = {
            "from_email": fields.get("from_email", ""),
            "to_email_list": mail.get("to_email_list") or [],
            "cc_email_list": mail.get("cc_email_list") or [],
        }
        task = {"task_id": tid, "session_id": tid + "-S", "threat_msg_id": fid,
                "from_email": fields.get("from_email", ""), "urgency_raw": fields.get("urgent", ""),
                "internal_status": "R_INIT", "external_status": "R_SEND", "status": "INIT",
                "mode": "ontology", "spare_info": into}
        store.upsert_task(task)
        store.audit("Task", tid, "claim", operator="emp-009", snapshot={"from": fields.get("from_email")})
        mg.mark_seen_by_message_id(fid)  # SEEN 认领握手：现轨 UNSEEN 不再处理
        claimed.append(tid)
    return claimed


# ── 入向回复归集：报价/审批/运单/工程师完成 ───────────────────────
def process_replies(mg):
    updates = []
    raw = mg.read_inbox(since_timestamp=int(time.time()) - 48 * 3600)
    mails = (raw or {}).get("mails", []) if isinstance(raw, dict) else (raw or [])
    tasks = {t["task_id"]: t for t in store.list_tasks()
             if (t.get("mode") == "ontology") and (t.get("status") not in _TERMINAL)}
    fresh = {}  # 逐任务最新工作副本，避免同任务多条回复互相覆盖
    for m in mails:
        inrep = (m.get("in_reply_to") or "") + " " + (m.get("references") or "")
        owner = None
        for tid, t in tasks.items():
            known = _mids_of(t)
            if known and any((">" in x or "" in x) and x.strip()[:60] in inrep or (x.strip() in inrep or x.strip().lstrip("<").rstrip(">") in inrep) for x in known):
                owner = t
                break
        if not owner:
            continue
        tid = owner["task_id"]
        cur = fresh.get(tid) or dict(owner)
        mid = (m.get("message_id") or "").strip()
        meta = dict(cur.get("spare_info") or {})
        rec = list(meta.get("received_reply_ids") or [])
        if mid in rec:
            continue
        rec.append(mid)
        body = (m.get("mail_body_text") or "")
        from_e = (m.get("from_email") or "").lower().strip()
        # 该邮件线程元数据（Reply-All 用）：原邮件 To/Cc/From 排除系统自身由 send 端处理
        mail_meta = {"from_email": (m.get("from_email") or "").strip(),
                     "to_email_list": m.get("to_email_list") or [],
                     "cc_email_list": m.get("cc_email_list") or []}
        emit = None
        if from_e == str(cur.get("from_email") or "").lower().strip() and any(k in body for k in _CLOSE_KW):
            meta["engineer_close"] = body[:500]
            meta["engineer_close_mid"] = mid
            meta["engineer_close_refs"] = (m.get("references") or "").strip()
            meta["engineer_close_reply_from"] = mail_meta
            emit = "engineer_close"
        elif from_e in [a.lower() for a in (meta.get("approver_emails") or [])] and any(k in body for k in _APPROVE_KW):
            # 审批人确认：按报价单最低价选定供应商（若尚未显式指定）
            qq = [q for q in (meta.get("quotes") or []) if q.get("email") and q.get("unit_price")]
            low = min(qq, key=lambda q: float(q.get("unit_price") or 10 ** 12)) if qq else None
            chosen = meta.get("target_supplier") or (low["email"] if low else "")
            meta["target_supplier"] = chosen
            meta["approval_choice"] = chosen
            emit = "approval"
        elif any(k in body for k in _SHIP_KW):
            mn = re.search(r"([A-Za-z]{0,6}[\d]{6,})", body)
            meta["tracking_no"] = mn.group(1) if mn else body[:80]
            meta["ship_raw"] = body
            meta["ship_mid"] = mid
            meta["ship_reply_from"] = mail_meta
            emit = "shipping"
        elif _price(body):
            quotes = meta.get("quotes") or []
            quotes.append({"email": from_e, "unit_price": _price(body), "raw": body,
                           "msg_id": mid, "refs": (m.get("references") or "").strip(),
                           "reply_all": mail_meta,
                           "receive_time": time.strftime("%Y-%m-%d %H:%M:%S")})
            meta["quotes"] = quotes; emit = "quote"
        meta["received_reply_ids"] = rec
        cur = {**cur, "spare_info": meta}
        store.upsert_task(cur)
        fresh[tid] = cur
        tasks[tid] = cur
        updates.append({"task_id": tid, "kind": emit})
    return updates


# ── 决策 + 执行 ───────────────────────────────────────────────────
def drive(mode="off", use_llm=False, mg=None):
    if mode not in ("ontology", "split"):
        return []
    reports = []
    g = execution.governor()
    trusted = bool(g.get("llm"))
    shadow = bool(g.get("llm") is False and os.getenv("ONT_SHADOW", "0") == "1")
    for t in store.list_tasks(limit=100):
        if t.get("mode") != "ontology" or t.get("status") in _TERMINAL:
            continue
        ctx = ctx_from_task(t)
        # 影子/信任模式都先算规则基准（参照系）
        rule_act, rule_reason, _ = _decide(ctx, t, False)
        chosen, reason, via_llm = rule_act, rule_reason, False
        aligned = True
        if trusted or shadow:
            llm_act, llm_reason, via2 = _decide(ctx, t, True)
            aligned = (llm_act == rule_act)
            store.audit("Task", t["task_id"], f"align:{llm_act}",
                        operator="emp-009",
                        snapshot={"rule": rule_act, "llm": llm_act, "aligned": aligned,
                                  "llm_reason": llm_reason[:200]},
                        remark="本体知识层 LLM 决策 影子对齐")
        if trusted and via_llm:
            chosen, reason, via_llm = (llm_act, llm_reason, True)
        ok, detail = execution.execute_action(chosen, t, ctx, mg=mg, force=False)
        reports.append({"task_id": t["task_id"], "action": chosen, "reason": reason[:40],
                        "via_llm": via_llm, "aligned": aligned, "ok": ok, "detail": detail})
    return reports


def _decide(ctx, task, use_llm):
    from .engine import decide_action
    return decide_action(ctx, use_llm=use_llm, task=task)


def _shake(s):
    import hashlib
    return hashlib.md5((s or "x").encode()).hexdigest()[:8].upper()


# ── 全流程：认领 + 回复 + 驱动 ────────────────────────────────────
def run_full(mg, use_llm=False):
    g = execution.governor()
    claimed = claim_inquiries(mg, g["mode"], g["roll"])
    replies = process_replies(mg)
    reports = drive(g["mode"], use_llm=use_llm, mg=mg)
    return {"claim": claimed, "replies": replies, "drive": reports, "governor": g}