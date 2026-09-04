# -*- coding: utf-8 -*-
"""LLM 决策 + 规则校验循环（DRV-R-01）+ 规则式兜底提议器。
Stage A（只读对照）：读事实→选动作→规则校验→只记录对齐结果，不执行副作用。
Stage B/C：dry_run=False 时执行动作（发送/落库），此处预留。
"""
import json

from . import knowledge
from app.config import settlement_enabled


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
    meta = task.get("spare_info") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
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
        # 定标模式：True=AI 自动比价直送审批；False=先交项目经理定标（人工轨）
        "auto_award": bool(meta.get("auto_award")),
        "pm_emails": meta.get("pm_emails") or [],
        "approval_choice": (task.get("approval_choice") or task.get("approval_params") or {}).get("supplier", "") if isinstance(task.get("approval_params"), dict) else (task.get("target_supplier") or ""),
        "tracking_number_candidate": task.get("shipped_no") or (task.get("shipped_mail_meta") or ""),
        # 收集/截止：以运行时 meta 的 deadline_passed 为准，叠加步骤字符串口径，确保两条路径一致
        "collection_done": _bool(task.get("latest_step", "").find("DECIDING") >= 0
                                 or task.get("external_status") in
                                 ("R_DECIDING", "R_WAIT_APPROVAL", "R_APPROVAL", "R_ORDER",
                                  "R_WAIT_ORDER", "R_WAIT_SHIPPING", "R_WAIT_ACCEPTANCE", "R_WAIT_SETTLE")
                                 or meta.get("deadline_passed") or meta.get("collection_done")),
        "deadline_passed": _bool(("超时" in str(task.get("latest_step", "")))
                                 or ("DECIDING" in str(task.get("latest_step", "")))
                                 or task.get("external_status") in
                                 ("R_DECIDING", "R_WAIT_APPROVAL", "R_APPROVAL", "R_ORDER",
                                  "R_WAIT_ORDER", "R_WAIT_SHIPPING", "R_WAIT_ACCEPTANCE", "R_WAIT_SETTLE")
                                 or meta.get("deadline_passed")),
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

    # 收集/超时判定
    collection_done = ctx.get("collection_done")
    valid_n = ctx.get("valid_quote_count") or 0
    raw_n = ctx.get("raw_quote_count") or 0
    deadline_passed = ctx.get("deadline_passed")

    # 审批驳回：显式中止，不再无限重发审批 D
    if ctx.get("approval_rejected"):
        return ("abortTask", "CLOSED_ABORT", internal, "审批驳回，任务中止")

    # 收到提前/含糊的"单号"邮件（非正式发货通知，如"补充单号"）→ 回复发货快递单号（仅一次）
    if ctx.get("premature_track_supplier") and not ctx.get("premature_track_replied"):
        return ("requestShippingTracking", ctx.get("external_status", ""), ctx.get("internal_status", ""),
                "收到非发货类单号邮件，回复发货快递单号")

    # S1 立项·尚未分发：有目标供应商 → 分发询价 B
    if external in ("R_SEND", "R_INIT") and (ctx.get("target_supplier_list") or []):
        return ("distributeInquiry", "INVITE_QUOTE", "R_INIT", "向目标供应商分发询价 B")

    # S2 询价收集阶段：收报价，直到收集结束/到期
    if external in ("R_SEND", "R_INIT", "INVITE_QUOTE", "R_WAIT_QUOTES"):
        if deadline_passed and valid_n == 0 and raw_n == 0:
            return ("abortTask", "CLOSED_ABORT", internal, "无任何报价且到期")
        # 收集阶段未结束且未到期 → 收报价/催补；
        # 截止时间到（deadline_passed）一律不再发催补邮件（没有就没有），直接收尾进审批
        if not collection_done and not deadline_passed:
            # 收到回复但解析失败 → 主动回信催促补全（≠无回复，不应干等）
            if ctx.get("unparseable_supplier_emails"):
                return ("requestQuoteClarification", external, internal,
                        "报价解析失败，催促供应商补全后重发")
            return ("receiveSupplierQuote", external, internal, "继续收集报价")
        # 收集结束且内部审批尚未发出 → 按定标模式分叉
        if internal != "R_APPROVAL":
            if ctx.get("auto_award"):
                # 自动轨：A 已声明「无特殊要求，最低价中标」→ AI 比价后直送审批。
                # 审批人只需回「确认采购」，process_replies 会自动沿用最低价（见 orbit 审批分支）。
                return ("submitApproval", "R_DECIDING", "R_APPROVAL", "自动轨：发起审批汇总 D")
            # 人工轨：未声明自动定标 → 报价汇总交项目经理定标，
            # PM 线下比选（可含特殊要求处理）后自行送审批，智能体不代发审批邮件。
            return ("requestPmDecision", "R_WAIT_PM", internal, "人工轨：报价交项目经理定标")
        # 审批已发出但仍滞留收集中（收尾）→ 确认下单
        if ctx.get("target_supplier"):
            return ("confirmOrderToSupplier", "R_ORDER", "R_APPROVAL", "审批选定，下达订货")
        return ("processApprovalDecision", external, "R_APPROVAL", "等待审批选择")

    # S2.5 人工轨·待定标：P 已发项目经理，等审批结论回流。
    # 中间环节（PM 线下比选 / 特殊要求处理 / 转交审批）智能体不感知，
    # 唯一推进信号是审批人在本线程内回复的「确认采购」（由 process_replies 写入 target_supplier）。
    # 若审批人另起新邮件回复，线程匹配失败 → 任务将长期滞留此态，需在看板上监控。
    if external == "R_WAIT_PM":
        if ctx.get("target_supplier"):
            return ("confirmOrderToSupplier", "R_ORDER", "R_APPROVAL", "人工轨：审批通过，下达订货")
        return ("processApprovalDecision", external, "R_APPROVAL", "等待项目经理定标后审批")

    # S3 审批阶段：等审批人选定/确认供应商 → 发出订货 E
    if external in ("R_APPROVAL", "R_DECIDING", "R_WAIT_APPROVAL"):
        if internal == "R_APPROVAL" and ctx.get("target_supplier"):
            return ("confirmOrderToSupplier", "R_ORDER", "R_APPROVAL", "审批合法，下达订货")
        return ("processApprovalDecision", external, "R_APPROVAL", "等待/处理审批选择")

    # S4 已下达订货：等待供应商发货通知，不在下单后立即主动催单号
    if external in ("R_ORDER", "R_WAIT_ORDER", "ORDER_CONFIRM"):
        if ctx.get("tracking_number_candidate"):
            return ("receiveTrackingNumber", "R_WAIT_SHIPPING", internal, "登记快递单号")
        # 仅当供应商称已发货但邮件里没解析到单号时，才回信索取一次
        if ctx.get("ship_no_tracking_candidate"):
            return ("requestTrackingNo", external, internal, "供应商称已发货但缺单号，索取")
        # 否则仅下单：等待供应商发货通知，不主动发"请回复发货快递单号"
        return ("waitForSupplierShipment", external, internal, "等待供应商发货通知")

    # S5 已发货：供应商已回传单号 → 当前版本流程即结束（无收货验收/结算步骤）。
    # 仅当结算开关开启(ONT_SETTLEMENT_ENABLED)时，才进入工程师确认→结算 G 闭环。
    if external in ("R_WAIT_SHIPPING", "R_WAIT_ENGINEER_CLOSE"):
        if settlement_enabled():
            if internal == "R_CLOSED":
                return ("engineerFinalClose", "R_SETTLE", "R_CLOSED", "工程师确认完成，发 G 结算")
            return ("receiveTrackingNumber", external, internal, "等待工程师确认/单号")
        # 当前版本（结算未启用）：供应商发货且单号已记录 = 流程结束
        return ("completeProcurement", "R_PROC_DONE", "R_CLOSED",
                "供应商已发货且单号已记录，当前版本流程结束")

    return ("finalizeQuoteCollection", external, internal, "维持现状")