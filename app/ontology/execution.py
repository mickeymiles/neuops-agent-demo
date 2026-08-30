# -*- coding: utf-8 -*-
"""动作执行器 + 治理开关（阶段 B）。
动作真正的执行（发信/建 O_Task/更新状态）都在此；是否真的发信/落库由 Governor 决定。
Governor 默认 'off'（不接管、不执行任何变更，零影响现轨）；灰度测试时再置 'split/all'。
默认全程 dry_run=False 但 Governor 未开时禁止执行。

复用：mail_gateway（只读复用现轨发信/收信 tool）、现轨审批人/供应商配置（只读）。
"""
import os
import time

from . import store, schema

# 治理：本轨是否接管任务并执行变更
_GOV = {"mode": os.getenv("ONT_MODE", "off"), "roll": float(os.getenv("ONT_ROLL", "0")), "exec": os.getenv("ONT_EXEC", "0") == "1"}


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
        to = [s.get("email") for s in ctx.get("target_supplier_list") or []]
        for email in to:
            mg.send_mail(to=[email],
                         subject=f"【询价】{ctx.get('part_type')} {ctx.get('brand')} {ctx.get('pn')} x {ctx.get('count')} — 请回复报价",
                         body_text=f"您好，请就以下备件报价：\n类型：{ctx.get('part_type')} 品牌：{ctx.get('brand')} PN：{ctx.get('pn')} 数量：{ctx.get('count')}\n请回复单价/货期/成色。\n- NeuOps 备件询价(emp-009)")
        store.upsert_task({**task, "external_status": "INVITE_QUOTE"})
        store.audit("Task", task["task_id"], "distributeInquiry", operator="emp-009", snapshot={"to": to})
        return True, "inquiry B sent"

    if action_id == "confirmOrderToSupplier" and mg:
        sel = ctx.get("target_supplier") or ""
        mg.send_mail(to=[sel],
                     subject=f"【订货确认】请安排发货",
                     body_text=f"请按已报价备件安排发货，并提供快递单号。\n- NeuOps 备件询价(emp-009)")
        store.upsert_task({**task, "external_status": "ORDER_CONFIRM"})
        store.audit("Task", task["task_id"], "confirmOrderToSupplier", operator="emp-009", snapshot={"supplier": sel})
        return True, "order E sent"

    if action_id == "submitApproval" and mg:
        mg.send_mail(to=[ctx.get("from_email")], cc=ctx.get("approver_emails") or [],
                     subject="【询价汇总】请审批",
                     body_text=f"最低价供应商：{ctx.get('target_supplier')}\n请回复确认。")
        store.upsert_task({**task, "internal_status": "R_APPROVAL"})
        store.audit("Task", task["task_id"], "submitApproval", operator="emp-009")
        return True, "approval D sent"

    if action_id in ("receiveTrackingNumber", "engineerFinalClose", "abortTask", "processApprovalDecision"):
        store.upsert_task({**task, "external_status": action_id,
                           "tracking_number": ctx.get("tracking_number_candidate", "")})
        store.audit("Task", task["task_id"], action_id, operator="emp-009")
        return True, f"{action_id} applied"

    store.audit("Task", task.get("task_id"), f"noop:{action_id}", operator="emp-009",
                remark="action has no executor yet")
    return False, f"no executor for {action_id}"