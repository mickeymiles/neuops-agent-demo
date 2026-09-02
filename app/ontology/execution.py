# -*- coding: utf-8 -*-
"""动作执行器 + 治理开关（阶段 B）。
动作真正的执行（发信/建 O_Task/更新状态）都在此；是否真的发信/落库由 Governor 决定。
Governor 默认 'off'（不接管、不执行任何变更，零影响现轨）；灰度测试时再置 'split/all'。
默认全程 dry_run=False 但 Governor 未开时禁止执行。

复用：mail_gateway（只读复用现轨发信/收信 tool）、现轨审批人/供应商配置（只读）。
"""
import os
import time
from datetime import datetime, timezone, timedelta

from . import store, mail_tpl

# 业务时区：与中国采购业务一致，所有"墙上时间"字符串用 GMT+8（见 orbit.BIZ_TZ，保持同步）。
BIZ_TZ = timezone(timedelta(hours=8))
from app.config import settlement_enabled

# 治理：本轨默认 off（不接管、不执行变更，零影响现轨，本体轨暂停改走传统状态机）。
# 需要时可用 ONT_MODE / ONT_EXEC / ONT_LLM 开启。
_GOV = {"mode": os.getenv("ONT_MODE", "off"), "roll": float(os.getenv("ONT_ROLL", "0")),
        "exec": os.getenv("ONT_EXEC", "0") == "1", "llm": os.getenv("ONT_LLM", "0") == "1"}

# 本体轨数字员工实体（与 registration.py 保持一致）
_EMP_ID = "emp-009"
_SKILL_ID = "skill-ont-proc-inquiry"


def set_governor(mode: str = "off", roll: float = 0.0, exec_enabled=False, llm: bool = None):
    """mode: off|legacy|ontology|split。roll∈[0,1]=分给本体轨比例。exec_enabled=允许真实发信/落库。
    llm=None 保持现值；True→LLM 决策接管并执行；False→规则驱动(可开影子对齐)。"""
    if mode not in ("off", "legacy", "ontology", "split"):
        raise ValueError("mode must be off|legacy|ontology|split")
    g = {"mode": mode, "roll": max(0.0, min(1.0, roll)), "exec": bool(exec_enabled)}
    if llm is not None:
        g["llm"] = bool(llm)
    _GOV.update(g)
    return dict(_GOV)


def governor():
    return dict(_GOV)


def _employee_managed() -> bool:
    """数字员工 emp-009 及其关联技能在 DB 中是否启用。

    这是「开关在数字员工身上」的真实生效点：页面/监控页把 employees.enabled 置否，
    运行时即停止执行（无需改 .env / 脚本 / 重启）。

    向后兼容：员工实体尚未注册（测试库/旧库）时按历史默认放行。
    """
    try:
        from app.db.employees import db_get_employee
        emp = db_get_employee(_EMP_ID)
    except Exception:
        return True
    if emp is None:
        return True
    if not emp.get("enabled", True):
        return False
    if not (emp.get("skill_states") or {}).get(_SKILL_ID, True):
        return False
    return True


def _is_managed() -> bool:
    return _GOV["mode"] in ("ontology", "split") and _GOV["exec"] and _employee_managed()


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
    """本体轨自身发件邮箱（用于 Reply-All 排除）。

    必须取本体轨自己的邮箱（ONT_MAIL_*，即 b4）；若仍取现轨的 b3，
    Reply-All 时不会把 b4 自己排除，智能体会给自己发信造成自激循环。
    """
    try:
        from app.ontology.mail_gateway import _ont_mail_cfg
        return (_ont_mail_cfg() or {}).get("mail_username") or ""
    except Exception:
        return ""


def _cc_all(ctx, *extra):
    """统一的抄送名单构造函数（唯一来源，避免各处漏配）。

    规则（与业务约定一致）：
      抄送 = 系统配置审批人 + 首封询价 A 的抄送（全局携带）+ 系统配置抄送 + extra
    并做：去空、按邮箱小写去重、排除智能体自身邮箱（防自激循环）。

    extra 用于把「发起人」等本轮特定角色并入抄送（如 E/G 主送供应商时发起人改抄送）。
    """
    items = []
    items.extend(ctx.get("approver_emails") or [])
    items.extend(ctx.get("inquiry_cc") or [])
    items.extend(ctx.get("global_cc") or [])
    items.extend([e for e in extra if e])
    self_mail = (_self_email() or "").strip().lower()
    out, seen = [], set()
    for e in items:
        k = str(e or "").strip().lower()
        if not k or k in seen or k == self_mail:
            continue
        seen.add(k)
        out.append(str(e).strip())
    return out


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
                           "quote_deadline": datetime.fromtimestamp(_deadline(ctx.get("urgent")), tz=BIZ_TZ).strftime("%Y-%m-%d %H:%M:%S")})
        store.audit("Task", task["task_id"], "createTask", operator="emp-009", snapshot={"fields": ctx})
        return True, "task created"

    if action_id == "distributeInquiry" and mg:
        to = ctx.get("target_supplier_list") or []  # 已是 email 字符串列表
        b_mids = []
        by_sup = dict((task.get("spare_info") or {}).get("b_msg_by_supplier") or {})
        for email in to:
            subj, _body = mail_tpl.render("B", ctx, task)
            # B 抄送 = 审批人 + 首封 A 抄送 + 系统配置抄送（三路都要携带）
            r = mg.send_mail(to=[email], subject=subj, body_text=_body,
                             cc=_cc_all(ctx) or None)
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
        # E 订货：回复选中供应商报价(C)线程，携带其报价原文。
        # 主送=选中供应商，其余（发起人/审批人/观察者）一律抄送——不启用 Reply-All 的 To 合并，
        # 否则会把观察者也塞进主送。线程连续性由 reply_to/refs 保证。
        reply_to = (q.get("msg_id") or "").strip()
        refs = (q.get("refs") or "").strip() or ((meta.get("b_msg_by_supplier") or {}).get(sel) or "")
        ok, detail, r = _send_tpl(mg, "E", ctx, task, to=[sel],
                                  cc=_cc_all(ctx, ctx.get("from_email")),
                                  reply_to=reply_to or None, refs=refs or None,
                                  original_body=q.get("raw"))
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
                                  cc=_cc_all(ctx),
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
        # 供应商正式发货且单号已解析 → 登记物流，进入 R_WAIT_SHIPPING。
        # 幂等：tracking_number 已记录则不再重复 upsert/审计（避免每轮轮询刷屏）。
        meta = dict(task.get("spare_info") or {})
        cand = ctx.get("tracking_number_candidate", "") or meta.get("tracking_no", "")
        if meta.get("tracking_recorded_at") and task.get("tracking_number"):
            return True, "tracking already recorded (skip re-audit)"
        meta["tracking_recorded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # tracking_number 由 store_biz 映射落到业务列 logistics_no（前端读该列/其别名 shipped_no）
        store.upsert_task({**task, "external_status": "R_WAIT_SHIPPING",
                           "tracking_number": cand, "spare_info": meta})
        store.audit("Task", task["task_id"], "receiveTrackingNumber", operator="emp-009",
                    snapshot={"tracking_no": cand})
        return True, "tracking recorded"

    if action_id == "engineerFinalClose":
        meta = dict(task.get("spare_info") or {})
        # 结算闭环开关（ONT_SETTLEMENT_ENABLED，默认关闭）：不向供应商发 G 结算邮件，
        # 仅把任务标记 CLOSED（不再发送任何邮件），预留后续启用。
        if not settlement_enabled():
            store.upsert_task({**task, "external_status": "R_CLOSED", "internal_status": "R_CLOSED",
                               "status": "CLOSED", "spare_info": meta})
            store.audit("Task", task["task_id"], "engineerFinalClose", operator="emp-009",
                        snapshot={"skipped": "settlement disabled: G not sent"})
            return True, "settlement disabled: task closed without G"
        if mg:
            sup = ctx.get("target_supplier") or meta.get("target_supplier") or ""
            q = _sel_quote(meta, sup)
            # G 结算：回复选中供应商报价(C)线程，携带报价原文。
            # 主送=供应商，其余（发起人/审批人/观察者）一律抄送——不启用 Reply-All 的 To 合并。
            # 线程连续性由 reply_to/refs 保证。
            reply_to = (q.get("msg_id") or "").strip()
            refs = (q.get("refs") or "").strip()
            orig = (q.get("raw") or "") + "\n" + (meta.get("ship_raw") or "")
            ok, detail, r = _send_tpl(mg, "G", ctx, task, to=[sup] if sup else [ctx.get("from_email")],
                                      cc=_cc_all(ctx, ctx.get("from_email")),
                                      reply_to=reply_to or None, refs=refs or None,
                                      original_body=orig)
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
                      cc=_cc_all(ctx),
                      reply_to=(meta.get("inquiry_mid") or "").strip() or None,
                      refs=((meta.get("inquiry_refs") or "") + " " +
                            (meta.get("inquiry_mid") or "")).strip() or None,
                      original_body=meta.get("inquiry_raw"))
        store.upsert_task({**task, "external_status": "CLOSED_ABORT", "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "abortTask", operator="emp-009")
        return True, "task aborted"

    if action_id == "requestQuoteClarification" and mg:
        un = ctx.get("unparseable_supplier_emails") or []
        meta = dict(task.get("spare_info") or {})
        by_sup = meta.get("b_msg_by_supplier") or {}
        # 已催补记录：{email: [缺失字段key]}；同供应商、且缺失项未变化才跳过重发，避免每轮刷屏。
        asked = {str(k).lower(): v for k, v in (meta.get("clarification_requested") or {}).items()}
        quotes = meta.get("quotes") or []
        by_email = {str(q.get("email") or "").strip().lower(): q for q in quotes}
        _QFIELDS = (("unit_price", "单价"), ("delivery", "货期"),
                    ("condition", "成色"), ("quantity", "数量"))
        sent = []
        for email in un:
            ke = str(email).strip().lower()
            q = by_email.get(ke, {})
            miss = [key for key, _ in _QFIELDS if not str(q.get(key) or "").strip()]
            if not miss:
                # 四项其实都齐了（多为先报价后补货期被重新识别），不再重复催
                asked.pop(ke, None)
                continue
            # 缺失项与上次完全一致 → 已催过，跳过（防重复发信）
            if ke in asked and set(asked[ke]) == set(miss):
                continue
            labels = [label for key, label in _QFIELDS if key in miss]
            bmid = (by_sup.get(str(email).strip()) or "")
            subj = "Re: 【询价】报价信息不完整，请补充后重发"
            body = ("您好，收到您的回复，但以下报价字段仍缺失，请补全后重发：\n- "
                    + "\n- ".join(labels)
                    + f"\n\n备件：{ctx.get('part_type')} {ctx.get('brand')} {ctx.get('pn')} x {ctx.get('count')}\n"
                    f"任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
            mg.send_mail(to=[email], subject=subj, body_text=body,
                         reply_to_mail_id=bmid or None, reply_refs_chain=bmid or None)
            asked[ke] = miss
            sent.append(email)
        # 幂等：本轮既没发信、催补台账也没变化 → 静默返回，不写 upsert/审计。
        # （此前发信已去重但审计仍每轮追加，线上单任务刷出 36 条同名日志。）
        prev = {str(k).lower(): sorted(v or []) for k, v in
                (task.get("spare_info") or {}).get("clarification_requested", {}).items()} \
            if isinstance(task.get("spare_info"), dict) else {}
        cur = {k: sorted(v or []) for k, v in asked.items()}
        if not sent and prev == cur:
            return True, "clarification already requested (skip re-audit)"
        meta["clarification_requested"] = asked
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "requestQuoteClarification", operator="emp-009",
                    snapshot={"suppliers": un, "sent": sent, "asked": asked})
        return True, "clarification requested" + ("" if sent else " (all deduped)")

    if action_id == "processApprovalDecision":
        # 等待/处理审批选择。审批未回时每轮都会命中该动作，
        # 幂等：仅当"审批选择结果"发生变化时才写审计，否则静默（避免每 60s 刷同一条）。
        meta = dict(task.get("spare_info") or {})
        sup = ctx.get("target_supplier", "") or ctx.get("approval_choice", "")
        if meta.get("approval_logged_choice") == sup and meta.get("approval_logged_at"):
            return True, "approval decision unchanged (skip re-audit)"
        meta["target_supplier"] = sup
        meta["approval_logged_choice"] = sup
        meta["approval_logged_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "internal_status": "R_APPROVAL", "spare_info": meta})
        store.audit("Task", task["task_id"], "processApprovalDecision", operator="emp-009",
                    snapshot={"target_supplier": sup})
        return True, "approval decision recorded"

    if action_id == "requestMissingFields" and mg:
        # 立项阶段缺必填字段 → 给工程师回信指出缺失项（仅一次）
        meta = dict(task.get("spare_info") or {})
        if meta.get("missing_requested"):
            # 幂等：不再写"跳过重发"审计（此前每轮都写，等于把刷屏换了个措辞）
            return True, "missing-fields already requested"
        try:
            from . import knowledge
            ok, failed = knowledge.check_target("createTask", ctx)
            miss = [f.get("missing") for f in (failed or []) if f.get("missing")] or ["部分必填字段"]
        except Exception:
            miss = ["部分必填字段"]
        subj = "Re: 询价信息不完整，请补充后重发"
        body = ("您好，收到您的采购询价，但以下必填信息缺失，请补全后重发：\n- "
                + "\n- ".join(miss)
                + f"\n\n任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
        mg.send_mail(to=[ctx.get("from_email")], subject=subj, body_text=body,
                     reply_to_mail_id=meta.get("inquiry_mid") or None,
                     reply_refs_chain=meta.get("inquiry_mid") or None)
        meta["missing_requested"] = True
        store.upsert_task({**task, "internal_status": "R_FR02_MISSING_FIELDS", "spare_info": meta})
        store.audit("Task", task["task_id"], "requestMissingFields", operator="emp-009",
                    snapshot={"missing": miss})
        return True, "missing fields requested"

    if action_id == "requestTrackingNo" and mg:
        # 供应商回"已发货"但无单号 → 主动索取（仅一次）
        meta = dict(task.get("spare_info") or {})
        if meta.get("tracking_requested_at"):
            return True, "tracking no already requested"
        sup = ctx.get("target_supplier") or meta.get("target_supplier") or ""
        if not sup:
            return False, "no target supplier for tracking request"
        subj = "Re: 请回复发货快递单号"
        body = ("您好，已收到贵司发货通知，请提供快递单号以便跟踪物流。\n"
                f"任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
        mg.send_mail(to=[sup], subject=subj, body_text=body,
                     reply_to_mail_id=meta.get("e_msg_id") or None,
                     reply_refs_chain=meta.get("e_msg_id") or None)
        meta["tracking_requested_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "requestTrackingNo", operator="emp-009",
                    snapshot={"supplier": sup})
        return True, "tracking no requested"

    if action_id == "requestShippingTracking" and mg:
        # 供应商发了含糊/提前的"单号"邮件（非发货通知）→ 回复发货快递单号（仅一次）
        meta = dict(task.get("spare_info") or {})
        if meta.get("premature_track_requested_at"):
            return True, "shipping tracking already requested"
        sup = (ctx.get("premature_track_supplier") or ctx.get("target_supplier")
               or meta.get("target_supplier") or "")
        if not sup:
            return False, "no supplier for shipping tracking request"
        subj = "Re: 请回复发货快递单号"
        body = ("您好，收到您补充的单号，但暂未收到正式发货通知及有效快递单号，"
                "请回复正式发货的快递单号以便跟踪物流。\n"
                f"任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
        mg.send_mail(to=[sup], subject=subj, body_text=body,
                     reply_to_mail_id=meta.get("premature_track_mid") or None,
                     reply_refs_chain=meta.get("premature_track_mid") or None)
        meta["premature_track_requested_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "requestShippingTracking", operator="emp-009",
                    snapshot={"supplier": sup})
        return True, "shipping tracking requested"

    if action_id == "receiveSupplierQuote":
        # 报价收集由 process_replies 内联完成；此处仅落审计，避免 noop 误报。
        # 幂等：仅在首次进入收集态记录一次，避免每轮(约60s)轮询都追加相同日志刷屏。
        meta = dict(task.get("spare_info") or {})
        if meta.get("collecting_logged"):
            return True, "quote collection active (already logged, skip re-audit)"
        meta["collecting_logged"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "receiveSupplierQuote", operator="emp-009",
                    remark="报价收集中（process_replies 已记录报价）")
        return True, "quote received (recorded in process_replies)"

    if action_id == "finalizeQuoteCollection":
        # 决策层兜底分支（"维持现状"）。纯 no-op，此前每轮(约60s)都写审计 → 页面刷屏。
        # 幂等：同一 (外部流/内部流) 状态只记一次；状态变化后允许再记一次。
        meta = dict(task.get("spare_info") or {})
        sig = "%s/%s" % (task.get("external_status") or "", task.get("internal_status") or "")
        if meta.get("finalize_logged_sig") == sig:
            return True, "collection finalized (already logged for this state, skip re-audit)"
        meta["finalize_logged_sig"] = sig
        meta["finalize_logged_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "finalizeQuoteCollection", operator="emp-009",
                    remark="维持现状（%s）" % sig)
        return True, "collection finalized (no-op state)"

    if action_id == "waitForSupplierShipment":
        # 已下单、供应商尚未发货通知：仅等待，不主动发"请回复发货快递单号"。
        # 幂等：仅在首次进入等待态记录一次，避免每轮(约60s)轮询都追加相同日志刷屏
        # （此前因每轮都 audit，导致页面"等待供应商发货"条目不停刷出）。
        meta = dict(task.get("spare_info") or {})
        if meta.get("waiting_shipment_logged"):
            return True, "waiting for supplier shipment (already logged, skip re-audit)"
        meta["waiting_shipment_logged"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "waitForSupplierShipment", operator="emp-009",
                    remark="已下达订货，等待供应商发货通知")
        return True, "waiting for supplier shipment (no email sent)"

    if action_id == "completeProcurement":
        # 当前版本收口：供应商已发货且单号已记录 → 流程结束（无收货验收/结算步骤）。
        # 与结算开关解耦：即便将来开启结算，此动作仅在 ONT_SETTLEMENT_ENABLED 关闭时由决策层调用。
        # 幂等：仅首次收口记录一次，之后每轮轮询静默跳过（置终态后 drive 也不再处理）。
        meta = dict(task.get("spare_info") or {})
        if meta.get("proc_completed_at"):
            return True, "procurement already completed (skip re-audit)"
        meta["proc_completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "external_status": "R_PROC_DONE", "internal_status": "R_CLOSED",
                           "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "completeProcurement", operator="emp-009",
                    remark="供应商已发货且单号已记录，当前版本流程结束（无收货验收/结算）")
        return True, "procurement completed at tracking (current version)"

    if action_id == "manualCloseTask":
        # 后台操作员手动关闭/取消（不在邮件链路）：写审计 + 置终态
        meta = dict(task.get("spare_info") or {})
        meta["manual_close"] = True
        meta["manual_close_reason"] = ctx.get("manual_close_reason", "")
        meta["manual_close_operator"] = ctx.get("operator", "web")
        store.upsert_task({**task, "external_status": "CLOSED_MANUAL", "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "manualCloseTask", operator=ctx.get("operator", "web"),
                    snapshot={"reason": meta["manual_close_reason"]})
        return True, "task manually closed"

    # 兜底：动作无执行器（多为邮件网关未就绪导致 `and mg` 未命中）。
    # 幂等：同一动作只记一次 noop，否则每轮(约60s)都会追加 noop:xxx 刷屏。
    meta = dict(task.get("spare_info") or {})
    noops = list(meta.get("noop_logged") or [])
    if action_id in noops:
        return False, f"no executor for {action_id} (already logged)"
    noops.append(action_id)
    meta["noop_logged"] = noops
    store.upsert_task({**task, "spare_info": meta})
    store.audit("Task", task.get("task_id"), f"noop:{action_id}", operator="emp-009",
                remark="action has no executor yet")
    return False, f"no executor for {action_id}"