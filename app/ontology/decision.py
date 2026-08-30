# -*- coding: utf-8 -*-
"""LLM 决策 + 规则校验循环（DRV-R-01）+ 规则式兜底提议器。
Stage A（只读对照）：读事实→选动作→规则校验→只记录对齐结果，不执行副作用。
Stage B/C：dry_run=False 时执行动作（发送/落库），此处预留。
"""
import json
import os

from . import knowledge, actions as act, store


def _bool(v):
    return bool(v)


# ── 从现轨 spare_mail_task 镜像为本体轨事实（只读，不改现轨）──────────
def build_fact_context(task: dict) -> dict:
    qjson = task.get("quotes_json") or []
    if isinstance(qjson, str):
        try:
            qjson = json.loads(qjson)
        except Exception:
            qjson = []
    sjson = task.get("suppliers_json") or []
    if isinstance(sjson, str):
        try:
            sjson = json.loads(sjson)
        except Exception:
            sjson = []
    valid_quotes = [q for q in qjson if q.get("parse_failed") is not True]
    target_emails = [s.get("email", "") for s in sjson if s.get("email")]

    ctx = {
        # 必填字段
        "project_no": task.get("project_no"), "project_name": task.get("project_name"),
        "part_type": task.get("part_type"), "brand": task.get("brand"), "pn": task.get("pn"),
        "spec": task.get("spec"), "condition": task.get("condition"), "count": task.get("count"),
        "address": task.get("address"), "urgent": task.get("urgent"),
        # 状态
        "internal_status": task.get("internal_status"),
        "external_status": task.get("external_status"),
        # 供应商/报价
        "target_supplier_list": target_emails,
        "valid_quotes": valid_quotes,
        "valid_quote_count": len(valid_quotes),
        "raw_quote_count": len(qjson),
        "valid_supplier_emails": [q.get("email", "") for q in valid_quotes if q.get("email")],
        "target_supplier": task.get("target_supplier") or "",
        "approval_choice": (task.get("approval_choice") or task.get("approval_params") or {}).get("supplier", "") if isinstance(task.get("approval_params"), dict) else (task.get("target_supplier") or ""),
        "tracking_number_candidate": task.get("shipped_no") or (task.get("shipped_mail_meta") or ""),
        # 收集/截止
        "collection_done": _bool(task.get("latest_step", "").find("DECIDING") >= 0
                                 or task.get("external_status") in
                                 ("R_DECIDING", "R_WAIT_APPROVAL", "R_APPROVAL", "R_ORDER",
                                  "R_WAIT_ORDER", "R_WAIT_SHIPPING", "R_WAIT_ACCEPTANCE", "R_WAIT_SETTLE")),
        "deadline_passed": _bool(("超时" in str(task.get("latest_step", "")))
                                 or ("DECIDING" in str(task.get("latest_step", "")))
                                 or task.get("external_status") in
                                 ("R_DECIDING", "R_WAIT_APPROVAL", "R_APPROVAL", "R_ORDER",
                                  "R_WAIT_ORDER", "R_WAIT_SHIPPING", "R_WAIT_ACCEPTANCE", "R_WAIT_SETTLE")),
    }
    if isinstance(task.get("approval_choice"), str) and task.get("approval_choice"):
        ctx["approval_choice"] = task["approval_choice"]
    return ctx


# ── 规则式提议器：根据事实选动作（确定性的，作为 LLM 兜底/对照基线）─────
def propose_action(ctx: dict):
    """返回 (action_id, next_external, next_internal, reason)。"""
    ok, failed = knowledge.check_target("createTask", ctx)
    if not ok:
        # 缺必填 → 若内部状态还是 R_INIT/未开单则回信补齐；否则维持
        return ("requestMissingFields", ctx.get("external_status", ""),
                "R_FR02_MISSING_FIELDS",
                ";".join(f["missing"] for f in failed) or "required fields missing")

    internal = ctx.get("internal_status") or "R_INIT"
    external = ctx.get("external_status") or "R_SEND"

    # 新建任务、尚未分发询价 → 谈 distributeInquiry（发 B）
    if external in ("R_SEND", "R_INIT") and (ctx.get("target_supplier_list") or []):
        return ("distributeInquiry", "INVITE_QUOTE", "R_INIT", "向目标供应商分发询价 B")

    # 收集/超时判定
    collection_done = ctx.get("collection_done")
    valid_n = ctx.get("valid_quote_count") or 0
    raw_n = ctx.get("raw_quote_count") or 0
    deadline_passed = ctx.get("deadline_passed")

    if external in ("R_WAIT_QUOTES", "INVITE_QUOTE", "R_SEND", "R_INIT"):
        if deadline_passed and valid_n == 0 and raw_n == 0:
            return ("abortTask", "CLOSED_ABORT", internal, "无任何报价且到期")
        if not collection_done and not deadline_passed:
            return ("receiveSupplierQuote", external, internal, "继续收集报价")

    if external == "R_WAIT_QUOTES" or (collection_done and valid_n > 0):
        if internal == "R_INIT":
            return ("submitApproval", "R_DECIDING", "R_APPROVAL", "发起审批汇总 D")
        # 审批已发
        ok, _ = knowledge.check_target("approval_valid", ctx)
        if ok and ctx.get("target_supplier"):
            return ("confirmOrderToSupplier", "R_ORDER", "R_APPROVAL", "审批合法，下达订货")
        if external in ("R_DECIDING", "R_WAIT_APPROVAL"):
            return ("processApprovalDecision", external, "R_APPROVAL", "等待/处理审批选择")

    if external in ("R_ORDER", "R_WAIT_ORDER"):
        if ctx.get("tracking_number_candidate"):
            return ("receiveTrackingNumber", "R_WAIT_SHIPPING", internal, "登记快递单号")
        return ("requestTrackingNo", "R_ORDER", internal, "回执无单号，主动索取")

    if external == "R_WAIT_SHIPPING":
        if internal == "R_CLOSED":
            return ("engineerFinalClose", "R_SETTLE", "R_CLOSED", "工程师确认完成，发 G 结算")
        return ("receiveTrackingNumber", external, internal, "等待供应商单号")

    return ("finalizeQuoteCollection", external, internal, "维持现状")