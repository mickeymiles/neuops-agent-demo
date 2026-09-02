# -*- coding: utf-8 -*-
"""动作注册表（ACT-R-01）：集中声明智能体可执行动作。
每个动作：{id, desc, target_status(执行后状态), effects, dry_run 可演示}。
执行动作所需的确定性能力（发信/收信/解析/落库）在 mail_gateway / store 中，
LLM 只做选择与编排（DET-R-01）。
"""
ACTION_REGISTRY = {
    "requestMissingFields": {
        "desc": "回信指出缺失必填字段，不建任务、不询价",
        "kind": "internal_reply",
        "next_internal": "R_FR02_MISSING_FIELDS",
    },
    "createTask": {
        "desc": "工程师询价字段齐全 → 建任务，生成 taskId 并计算 quoteDeadline",
        "kind": "create",
        "next_internal": "R_INIT",
        "next_external": "R_SEND",
    },
    "distributeInquiry": {
        "desc": "向目标供应商列表分发明文 B（不含收货地址），外部流进入 INVITE_QUOTE",
        "kind": "send",
        "next_external": "INVITE_QUOTE",
    },
    "receiveSupplierQuote": {
        "desc": "匹配 B 线程的供应商回复，生成 SupplierQuote 并标记 isValid/isTimeout",
        "kind": "process",
    },
    "finalizeQuoteCollection": {
        "desc": "决策兜底：无可推进动作时维持现状（不改状态，同一状态只记一次审计）",
        "kind": "state",
    },
    "requestQuoteClarification": {
        "desc": "供应商回复解析失败 → 回信催促按格式补全后重发，状态不变",
        "kind": "send",
    },
    "submitApproval": {
        "desc": "生成汇总审批 D、发送内部流 → APPROVAL_WAIT（抄送审批人+系统抄送）",
        "kind": "send",
        "next_internal": "R_APPROVAL",
    },
    "processApprovalDecision": {
        "desc": "解析审批回复，校验 ∈ 有效候选池，非法回信重选，合法写入 target_supplier",
        "kind": "process",
    },
    "confirmOrderToSupplier": {
        "desc": "向选中供应商发订货 E（含地址/数量/原报价），外部流 → ORDER_CONFIRM",
        "kind": "send",
        "next_external": "ORDER_CONFIRM",
    },
    "waitForSupplierShipment": {
        "desc": "已下达订货、供应商尚未发货通知 → 纯等待，不发信（只在进入等待态时记一次审计）",
        "kind": "state",
    },
    "receiveTrackingNumber": {
        "desc": "解析供应商快递单号写入 trackingNumber（落业务列 logistics_no）→ R_WAIT_SHIPPING",
        "kind": "process",
        "next_external": "R_WAIT_SHIPPING",
    },
    "requestTrackingNo": {
        "desc": "供应商回发货无单号 → 主动邮件索取，保持 ORDER_CONFIRM",
        "kind": "send",
    },
    "requestShippingTracking": {
        "desc": "收到非发货类的'单号'邮件 → 回信索取正式发货快递单号（仅一次），状态不变",
        "kind": "send",
    },
    "completeProcurement": {
        "desc": "【当前版本终态】供应商已发货且单号已记录 → 流程结束，不做收货验收/结算。"
                "仅在 ONT_SETTLEMENT_ENABLED 关闭时由决策层选中",
        "kind": "state",
        "next_internal": "R_CLOSED",
        "next_external": "R_PROC_DONE",
    },
    "engineerFinalClose": {
        "desc": "【需开启结算开关】工程师反馈测试完成 → 发 G 结算邮件，任务 CLOSED（全流程终态）",
        "kind": "send",
        "next_internal": "R_CLOSED",
        "next_external": "R_SETTLE",
    },
    "abortTask": {
        "desc": "无有效报价/全部拒绝 → 任务中止，CLOSED",
        "kind": "state",
        "next_external": "CLOSED_ABORT",
    },
    "manualCloseTask": {
        "desc": "后台有权限操作员手动关闭/取消，写审计（不在邮件链路）",
        "kind": "state",
        "next_external": "CLOSED_MANUAL",
    },
}


def get_action(action_id: str):
    return ACTION_REGISTRY.get(action_id)


def list_action_ids():
    return list(ACTION_REGISTRY.keys())