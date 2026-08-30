# -*- coding: utf-8 -*-
"""动作执行器 + 治理开关（阶段 B）。
动作真正的执行（发信/建 O_Task/更新状态）都在此；是否真的发信/落库由 Governor 决定。
Governor 默认 'off'（不接管、不执行任何变更，零影响现轨）；灰度测试时再置 'split/all'。
默认全程 dry_run=False 但 Governor 未开时禁止执行。

复用：mail_gateway（只读复用现轨发信/收信 tool）、现轨审批人/供应商配置（只读）。
"""
import os
import time

from . import store, schema, mail_tpl

# 治理：本轨是否接管任务并执行变更。默认 ontology+exec（切主后 emp-009 为唯一采购邮件轨）；
# 可用 ONT_MODE=off / ONT_EXEC=0 回退到仅诊断。
_GOV = {"mode": os.getenv("ONT_MODE", "ontology"), "roll": float(os.getenv("ONT_ROLL", "0")), "exec": os.getenv("ONT_EXEC", "1") == "1"}


def set_governor(mode: str = "off", roll: float = 0.0, exec_enabled: bool = False):
    """mode: off|legacy|ontology|split。roll∈[0,1] = 分给本体轨的比例。exec_enabled=允许真实发信/落库。"""
    if mode not in ("off", "legacy", "ontology", "split"):
        raise ValueError("mode must be off|legacy|ontology|split")
    _GOV.update({"mode": mode, "roll": max(0.0, min(1.0, roll)), "exec": bool(exec_enabled)})
    return dict(_GOV)


def governor():
    return dict(_GOV)


def _is_managed() -> bool:
    return _GOV["mode"] in ("ontology", "split") and _GOV["exec"]


def needs_exec(force: bool = False) -> bool:
    if force:
        return True
    return _is_managed()


def _deadline(urgent_raw: str):
    """时长换算（DET-R-01 确定性代码，不交 LLM）：xHH/xMN/xD 或 latest xh/x天。失败兜底24h。"""
    s = (urgent_raw or "").strip().lower()
    try:
        if not s:
            return int(time.time()) + 24 * 3600
        num = int(re_num(s))
        if "d" in s or "天" in s:
            return int(time.time()) + num * 86400
        if "mn" in s or "min" in s or "分" in s:
            return int(time.time()) + num * 60
        if "h" in s or "小" in s:
            return int(time.time()) + num * 3600
        return int(time.time()) + num * 3600
    except Exception:
        return int(time.time()) + 24 * 3600


import re as _re
def re_num(s):
    m = _re.search(r"\d+", s)
    return m.group(0) if m else "1"


def _suppliers_from_config(cfg_leak):
    return cfg_leak or []


def _self_email():
    """系统自身发件邮箱（用于 Reply-All 排除）。"""
    try:
        from app.mcp_tools import _proc_mail_cfg
        return (_proc_mail_cfg() or {}).get("mail_username") or ""
    except Exception:
        return ""


def _send_tpl(mg, tpl_key, ctx, task, *, to, cc=None, reply_to=None, refs=None,
              original_body=None, reply_all_from=None):
    """按模板渲染并发信；携带原文（===）、线程头（In-Reply-To/References）、可选 Reply-All。
    返回 (ok, detail, sent_r)。"""
    subj, body = mail_tpl.render(tpl_key, ctx, task)
    if original_body:
        body += mail_tpl.quote_orig(original_body)
    if reply_all_from:
        to, cc = mail_tpl.reply_recipients(reply_all_from, to, cc=cc, self_email=_self_email())
    r = mg.send_mail(to=to, subject=subj, body_text=body, cc=cc or None,
                     reply_to_mail_id=reply_to or None, reply_refs_chain=refs or None)
    return True, f"mail {tpl_key} sent", (r or {})


def _sel_quote(meta, target):
    """按选中供应商邮箱取对应报价（含 msg_id/refs/raw/reply_all）。"""
    for q in (meta.get("quotes") or []):
        if str(q.get("email") or "").strip().lower() == str(target or "").strip().lower():
            return q or {}
    return {}


def execute_action(action_id: str, task: dict, ctx: dict, mg=None, force: bool = False, log=print):
    """执行一个动作。task 为 O_Task 镜像。返回 (ok, detail)。未包治理时只审计不执行。"""
    if not needs_exec(force):
        store.audit("Task", task.get("task_id"), f"block:{action_id}", operator="emp-009",
                    remark=f"governor={_GOV['mode']}/exec={_GOV['exec']}，未放行")
        return False, f"governor未放行 mode={_GOV['mode']}"

    if action_id == "createTask":
        store.upsert_task({**task, "status": "INIT", "mode": "ontology",
                           "quote_deadline": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_deadline(ctx.get("urgent"))))})
        store.audit("Task", task["task_id"], "createTask", operator="emp-009", snapshot={"fields": ctx})
        return True, "task created"

    if action_id == "distributeInquiry" and mg:
        to = ctx.get("target_supplier_list") or []  # 已是 email 字符串列表
        b_mids = []
        by_sup = dict((task.get("spare_info") or {}).get("b_msg_by_supplier") or {})
        for email in to:
            subj, _body = mail_tpl.render("B", ctx, task)
            r = mg.send_mail(to=[email], subject=subj, body_text=_body)
            _mid = (r or {}).get("message_id") or (r or {}).get("msg_id") if isinstance(r, dict) else ""
            if _mid:
                b_mids.append(_mid)
                by_sup[str(email).strip()] = _mid
        meta = dict(task.get("spare_info") or {})
        meta["b_msg_ids"] = list(dict.fromkeys(list(meta.get("b_msg_ids") or []) + b_mids))
        meta["b_msg_by_supplier"] = by_sup
        store.upsert_task({**task, "external_status": "INVITE_QUOTE", "spare_info": meta})
        store.audit("Task", task["task_id"], "distributeInquiry", operator="emp-009", snapshot={"to": to, "b_mids": b_mids})
        return True, "inquiry B sent"

    if action_id == "confirmOrderToSupplier" and mg:
        sel = str(ctx.get("target_supplier") or "").strip()
        meta = dict(task.get("spare_info") or {})
        q = _sel_quote(meta, sel)
        # E 订货：回复选中供应商报价(C)线程，携带其报价原文；外部流 Reply-All 全员回复
        reply_to = (q.get("msg_id") or "").strip()
        refs = (q.get("refs") or "").strip() or ((meta.get("b_msg_by_supplier") or {}).get(sel) or "")
        ok, detail, r = _send_tpl(mg, "E", ctx, task, to=[sel],
                                  cc=[ctx.get("from_email")] + (ctx.get("approver_emails") or []),
                                  reply_to=reply_to or None, refs=refs or None,
                                  original_body=q.get("raw"),
                                  reply_all_from=q.get("reply_all"))
        meta["e_msg_id"] = ((r or {}).get("message_id") or (r or {}).get("msg_id")
                            if isinstance(r, dict) else "") or meta.get("e_msg_id", "")
        store.upsert_task({**task, "external_status": "ORDER_CONFIRM", "internal_status": "R_APPROVAL", "spare_info": meta})
        store.audit("Task", task["task_id"], "confirmOrderToSupplier", operator="emp-009",
                    snapshot={"supplier": sel, "reply_to": reply_to, "refs": refs})
        return True, "order E sent"

    if action_id == "submitApproval" and mg:
        meta = dict(task.get("spare_info") or {})
        # D 内部流：回复工程师询价(A)线程，携带原始采购申请原文；To工程师 + Cc审批人
        ok, detail, r = _send_tpl(mg, "D", ctx, task, to=[ctx.get("from_email")],
                                  cc=ctx.get("approver_emails") or [],
                                  reply_to=(meta.get("inquiry_mid") or "").strip() or None,
                                  refs=((meta.get("inquiry_refs") or "") + " " +
                                        (meta.get("inquiry_mid") or "")).strip() or None,
                                  original_body=meta.get("inquiry_raw"))
        meta["d_msg_id"] = ((r or {}).get("message_id") or (r or {}).get("msg_id")
                            if isinstance(r, dict) else "") or meta.get("d_msg_id", "")
        store.upsert_task({**task, "internal_status": "R_APPROVAL", "external_status": "R_DECIDING", "spare_info": meta})
        store.audit("Task", task["task_id"], "submitApproval", operator="emp-009")
        return True, "approval D sent"

    if action_id == "receiveTrackingNumber":
        store.upsert_task({**task, "external_status": "R_WAIT_SHIPPING",
                           "tracking_number": ctx.get("tracking_number_candidate", "")})
        store.audit("Task", task["task_id"], "receiveTrackingNumber", operator="emp-009",
                    snapshot={"tracking_no": ctx.get("tracking_number_candidate", "")})
        return True, "tracking recorded"

    if action_id == "engineerFinalClose":
        meta = dict(task.get("spare_info") or {})
        if mg:
            sup = ctx.get("target_supplier") or meta.get("target_supplier") or ""
            q = _sel_quote(meta, sup)
            # G 结算：回复选中供应商报价(C)线程，携带报价原文；外部流 Reply-All 全员回复
            reply_to = (q.get("msg_id") or "").strip()
            refs = (q.get("refs") or "").strip()
            orig = (q.get("raw") or "") + "\n" + (meta.get("ship_raw") or "")
            ok, detail, r = _send_tpl(mg, "G", ctx, task, to=[sup] if sup else [ctx.get("from_email")],
                                      cc=[ctx.get("from_email")] + (ctx.get("approver_emails") or []),
                                      reply_to=reply_to or None, refs=refs or None,
                                      original_body=orig, reply_all_from=q.get("reply_all"))
            meta["g_msg_id"] = ((r or {}).get("message_id") or (r or {}).get("msg_id")
                                if isinstance(r, dict) else "") or meta.get("g_msg_id", "")
        store.upsert_task({**task, "external_status": "R_SETTLE", "internal_status": "R_CLOSED",
                           "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "engineerFinalClose", operator="emp-009",
                    snapshot={"tracking_number": meta.get("tracking_no", ""), "g_msg_id": meta.get("g_msg_id")})
        return True, "task closed + settlement G"

    if action_id == "abortTask":
        meta = dict(task.get("spare_info") or {})
        if mg:
            # F 中止：回复工程师询价(A)线程，携带原始采购申请原文；To工程师 + Cc审批人
            _send_tpl(mg, "F", ctx, task, to=[ctx.get("from_email")],
                      cc=ctx.get("approver_emails") or [],
                      reply_to=(meta.get("inquiry_mid") or "").strip() or None,
                      refs=((meta.get("inquiry_refs") or "") + " " +
                            (meta.get("inquiry_mid") or "")).strip() or None,
                      original_body=meta.get("inquiry_raw"))
        store.upsert_task({**task, "external_status": "CLOSED_ABORT", "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "abortTask", operator="emp-009")
        return True, "task aborted"

    if action_id == "processApprovalDecision":
        meta = dict(task.get("spare_info") or {})
        meta["target_supplier"] = ctx.get("target_supplier", "") or ctx.get("approval_choice", "")
        store.upsert_task({**task, "internal_status": "R_APPROVAL", "spare_info": meta})
        store.audit("Task", task["task_id"], "processApprovalDecision", operator="emp-009",
                    snapshot={"target_supplier": meta["target_supplier"]})
        return True, "approval decision recorded"

    store.audit("Task", task.get("task_id"), f"noop:{action_id}", operator="emp-009",
                remark="action has no executor yet")
    return False, f"no executor for {action_id}"