# -*- coding: utf-8 -*-
"""emp-008 备品备件采购询比价智能体 API 路由

设计原则：
1. Skill 业务逻辑（skill-proc-01~09）封装为内部函数 _skill_proc_XX，调用 mcp_tools 的真实工具
2. trigger endpoint 给 contract-compare-9006 工程调用（任务状态变更后触发智能体）
3. test endpoint 用于快速验证邮件/飞书/SQLite 工具是否正常
4. scheduler/tick endpoint 给外部定时器调用（systemd timer 或 main.py startup asyncio loop）
"""
import asyncio
import json
import os
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import config
from app.mcp_tools import (
    tool_read_inbox_mail,
    tool_send_mail,
    tool_batch_send_mail,
    tool_send_feishu_message,
    tool_send_feishu_card,
    tool_table_query,
    tool_table_insert,
    tool_table_update,
)

router = APIRouter(prefix="/api/procurement-agent", tags=["procurement-agent"])

# 飞书消息卡片构建辅助
PROC_WEB_URL = os.getenv("PROC_WEB_URL", "http://127.0.0.1:9006/procurement")


def _build_quote_list_elements(task: dict, extra: dict) -> list:
    """构建报价列表卡片元素：每个供应商一行 + 「选择此供应商」按钮"""
    tid = task.get("task_id", "")
    pn = task.get("project_name", "")
    sp = task.get("spare_part_model", "")
    qty = task.get("purchase_qty", "")
    quotes = task.get("replied_supplier_quotes", [])
    no_reply = task.get("no_reply_supplier", [])
    total = len(task.get("inquiry_supplier_list", []))
    replied = len(quotes)

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content":
            f"**任务ID：** {tid}\n**项目：** {pn}\n**备件：** {sp} × {qty}\n"
            f"**已回复：** {replied}/{total} 家" + (f"｜未回复：{len(no_reply)} 家" if no_reply else "")}},
        {"tag": "hr"},
    ]
    if not quotes:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "暂无供应商回复报价"}})
        elements.append({"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📋 前往平台"},
             "type": "default", "url": f"{PROC_WEB_URL}"}
        ]})
        return elements

    for q in quotes:
        sn = q.get("supplier_name", "")
        em = q.get("email", "")
        brand = q.get("brand", "-")
        model = q.get("model", "-")
        price = q.get("unit_price", 0)
        rt = q.get("reply_time", "")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
            f"**{sn}** <{em}>\n品牌：{brand}｜型号：{model}｜单价：¥{price}\n报价时间：{rt}"}})
        elements.append({"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": f"✅ 选择 {sn}"},
             "type": "primary", "value": {
                 "action": "confirm_purchase",
                 "task_id": tid,
                 "supplier_name": sn,
                 "supplier_email": em,
                 "deal_price": price,
                 "reply_mail_id": q.get("message_id", ""),
             }},
        ]})
        elements.append({"tag": "hr"})

    elements.append({"tag": "action", "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "📋 前往平台选型"},
         "type": "default", "url": f"{PROC_WEB_URL}"}
    ]})
    return elements


def _build_proc_card(task: dict, event: str, extra: dict = None) -> dict:
    """根据 event 类型构建飞书 Interactive Card"""
    extra = extra or {}
    tid = task.get("task_id", "")
    pn = task.get("project_name", "")
    cn = task.get("contract_no", "")
    sp = task.get("spare_part_model", "")
    qty = task.get("purchase_qty", "")
    dl = task.get("reply_deadline", "")
    status = task.get("task_status", "")

    cards = {
        "task_created": {
            "header": {"title": {"tag": "plain_text", "content": "✅ 询价任务已发起"},
                       "template": "blue"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n**项目：** {pn}\n**合同：** {cn}\n"
                    f"**备件：** {sp} × {qty}\n**报价截止：** {dl}"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "📋 查看详情"},
                     "type": "default", "url": f"{PROC_WEB_URL}"},
                ]},
            ]},
        "all_quote_done": {
            "header": {"title": {"tag": "plain_text", "content": "✅ 全部报价已收齐"},
                       "template": "green"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n全部供应商报价已回复完成，请前往平台完成选型确认。"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "💰 前往选型"},
                     "type": "primary", "url": f"{PROC_WEB_URL}"},
                ]},
            ]},
        "confirm_purchase": {
            "header": {"title": {"tag": "plain_text", "content": "✅ 选型确认完成"},
                       "template": "purple"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n**项目：** {pn}\n**选中供应商：** {extra.get('supplier_name','')}\n"
                    f"**成交单价：** {extra.get('deal_price','')}\n已自动发送采购确认邮件给供应商。"}},
            ]},
        "confirm_purchase_action": {
            "header": {"title": {"tag": "plain_text", "content": "🔔 供应商报价更新，请选型"},
                       "template": "orange"},
            "elements": [],  # 延迟填充，见下方 if
        },
        "purchase_confirmed": {
            "header": {"title": {"tag": "plain_text", "content": "✅ 采购已确认"},
                       "template": "green"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n**已选供应商：** {extra.get('supplier_name','')}\n"
                    f"**成交单价：** ¥{extra.get('deal_price','')}\n"
                    f"采购确认邮件已通过邮件线程发送给供应商。"}},
                {"tag": "note", "elements": [
                    {"tag": "plain_text",
                     "content": "按钮已置灰，如需修改请前往平台操作"},
                ]},
            ]},
        "delivery": {
            "header": {"title": {"tag": "plain_text", "content": "📦 供应商已发货"},
                       "template": "cyan"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n**发货时间：** {task.get('delivery_time','')}\n"
                    f"**物流单号：** {task.get('logistics_no','')}\n请现场工程师留意收货测试。"}},
            ]},
        "ledger_written": {
            "header": {"title": {"tag": "plain_text", "content": "🎉 流程闭环，台账已写入"},
                       "template": "green"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n采购流程已闭环，采购台账已更新完成。"}},
            ]},
        "test_failed": {
            "header": {"title": {"tag": "plain_text", "content": "🚨 收货测试失败"},
                       "template": "red"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n收货测试结果为失败，请人工处置（换货/重新询价）。"}},
            ]},
        "deadline_warn": {
            "header": {"title": {"tag": "plain_text", "content": "⚠️ 即将超时告警"},
                       "template": "orange"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n距离报价截止仅剩30分钟！\n"
                    f"**尚未回复供应商：** {extra.get('no_reply_names','')}\n请跟进供应商报价。"}},
            ]},
        "timeout": {
            "header": {"title": {"tag": "plain_text", "content": "🚨 询比价已超时"},
                       "template": "red"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n**超时未回复供应商：** {extra.get('timeout_names','')}\n"
                    f"请人工评估是否继续选型或重新询价。"}},
            ]},
        "task_canceled": {
            "header": {"title": {"tag": "plain_text", "content": "❌ 任务已取消"},
                       "template": "grey"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**任务ID：** {tid}\n**取消原因：** {task.get('cancel_reason','')}"}},
            ]},
    }
    card = cards.get(event, {"elements": [{"tag": "div", "text": {"tag": "lark_md", "content": str(task)}}]})
    card["config"] = {"wide_screen_mode": True}
    # 延迟填充报价列表（只在 confirm_purchase_action 时）
    if event == "confirm_purchase_action":
        card["elements"] = _build_quote_list_elements(task, extra)
    return card


# ════════════════════════════════════════════════════════════════
# Pydantic 请求模型
# ════════════════════════════════════════════════════════════════
class SupplierItem(BaseModel):
    name: str
    email: str


class QuoteItem(BaseModel):
    supplier_name: str = ""
    email: str = ""
    brand: str = ""
    model: str = ""
    unit_price: float = 0
    reply_time: str = ""


class TaskInstance(BaseModel):
    """完整 task 实例（contract 工程传过来）"""
    task_id: str
    project_id: str = ""
    project_name: str = ""
    contract_no: str = ""
    spare_part_model: str = ""
    purchase_qty: float = 0
    emergency_level: str = "4h"
    reply_deadline: str = ""
    inquiry_supplier_list: List[SupplierItem] = []
    replied_supplier_quotes: List[QuoteItem] = []
    no_reply_supplier: List[SupplierItem] = []
    selected_supplier: Optional[SupplierItem] = None
    deal_unit_price: float = 0
    delivery_time: str = ""
    logistics_no: str = ""
    test_result: Optional[str] = None
    task_status: str = ""
    cancel_reason: str = ""
    creator: str = "pm"
    create_time: str = ""


class SelectionBody(BaseModel):
    task: TaskInstance
    selected_supplier: SupplierItem
    deal_unit_price: float


class TestResultBody(BaseModel):
    task: TaskInstance
    test_result: str
    remark: str = ""


class CancelBody(BaseModel):
    task: TaskInstance
    cancel_reason: str


class TestMailBody(BaseModel):
    to: List[str]
    subject: str = "智能体测试邮件"
    body_text: str = "这是一封来自 emp-008 智能体的测试邮件。"


class TestFeishuBody(BaseModel):
    open_id: str = ""
    content: str = "emp-008 智能体测试消息"


# ════════════════════════════════════════════════════════════════
# 邮件模板（设计文档第 5 章）
# ════════════════════════════════════════════════════════════════
INQUIRY_MAIL_TPL = """您好：

现发起备品备件采购询价，请按如下需求提供报价。
项目名称：{project_name}
合同编号：{contract_no}
备件型号：{spare_part_model}
采购数量：{purchase_qty}

⚠️报价回复截止时间：{reply_deadline}
请在截止时间前回复本邮件，提供品牌、型号、单价。
逾期将视为放弃本次询价。

本邮件由智能采购智能体自动发出，请勿直接回复给机器人账号。
任务ID：{task_id}
"""

CONFIRM_MAIL_TPL = """您好：

针对任务ID:{task_id}询价，确认选择贵司供货。
项目：{project_name}
合同号：{contract_no}
备件型号：{spare_part_model}
数量：{purchase_qty}
成交单价：{deal_unit_price}

请尽快备货发货，发货后请回复本邮件告知发货时间、物流单号。
本邮件作为采购正式依据。

任务ID：{task_id}
"""

ACCEPTANCE_MAIL_TPL = """您好：

任务ID:{task_id} 备品备件已验收通过。
项目：{project_name}
合同号：{contract_no}
备件型号：{spare_part_model}
数量：{purchase_qty}
成交单价：{deal_unit_price}
供应商：{supplier_name}

现场工程师已完成硬件测试，结果为通过。
本次采购流程闭环，采购台账已更新。

任务ID：{task_id}
"""


# ════════════════════════════════════════════════════════════════
# 9 个 Skill 业务函数（内部）
# ════════════════════════════════════════════════════════════════
def _skill_proc_01_create_task(task: TaskInstance) -> dict:
    """创建询比价任务：contract 工程已完成 create_task 落库，neuops 端不需要重写，
    仅返回 task 实例给 skill-proc-02 使用。"""
    return {"skill": "skill-proc-01", "task_id": task.task_id, "status": "created", "task": task.dict()}


def _skill_proc_02_send_inquiry_mail(task: TaskInstance) -> dict:
    """组装&发送询价邮件 + 飞书通知项目经理任务已发起"""
    subject = f"【备品备件询价】{task.project_name}｜合同号：{task.contract_no}｜任务ID:{task.task_id}"
    body = INQUIRY_MAIL_TPL.format(
        project_name=task.project_name, contract_no=task.contract_no,
        spare_part_model=task.spare_part_model, purchase_qty=task.purchase_qty,
        reply_deadline=task.reply_deadline, task_id=task.task_id,
    )
    to_list = [s.email for s in task.inquiry_supplier_list]
    mail_r = tool_batch_send_mail(receiver_email_list=to_list, subject=subject, body_text=body)

    # 飞书通知项目经理任务已发起（交互卡片）
    feishu_r = {"success": False, "error": "open_id 未配置"}
    if config.PROC_FEISHU_PM_OPEN_ID:
        card = _build_proc_card(task.dict(), "task_created")
        feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

    return {"skill": "skill-proc-02", "mail": mail_r, "feishu": feishu_r}


def _skill_proc_03_parse_quote_mails(since_ts: int = 0) -> dict:
    """邮件报价解析监听：拉取供应商邮件，LLM 解析报价回填 task。
    简化版：先拉邮件返回，LLM 解析阶段后续接入（先用规则抽取）。
    """
    if not since_ts:
        since_ts = int(time.time()) - 600  # 默认最近 10 分钟
    # 查询所有进行中 task 的供应商邮箱作为过滤
    tasks_r = tool_table_query(table_key="procurement_task",
                               filter={"task_status": "询比价进行中"}, page_size=50)
    supplier_emails = []
    task_map = {}  # from_email(小写) → task dict（含 _supplier_name）
    if tasks_r.get("success"):
        for t in tasks_r.get("records", []):
            for s in json.loads(t.get("inquiry_supplier_list", "[]")):
                if s.get("email"):
                    supplier_emails.append(s["email"])
                    td = dict(t)
                    td["_supplier_name"] = s.get("name", "")
                    task_map[s["email"].lower()] = td
    # 去重
    supplier_emails = list(set(supplier_emails))
    if not supplier_emails:
        return {"skill": "skill-proc-03", "mails": [], "note": "无进行中任务，跳过"}

    mails_r = tool_read_inbox_mail(since_timestamp=since_ts,
                                   filter_sender_email_list=supplier_emails)
    if not mails_r.get("success"):
        return {"skill": "skill-proc-03", "error": mails_r.get("error"), "mails": []}

    # 解析报价邮件 + 更新 task + 发飞书卡片
    results = []
    for m in mails_r.get("mails", []):
        from_email = m.get("from_email", "")
        body = m.get("mail_body_text", "")
        msg_id = m.get("message_id", "")
        # 找到对应的 task
        task = task_map.get(from_email.lower())
        if not task:
            continue
        # 简单规则抽取报价
        unit_price = 0
        brand = ""
        model = ""
        for kw in ["单价:", "单价：", "报价:", "报价："]:
            if kw in body:
                idx = body.find(kw) + len(kw)
                price_str = ""
                for ch in body[idx:idx+20]:
                    if ch.isdigit() or ch == ".":
                        price_str += ch
                    else:
                        if price_str:
                            break
                if price_str:
                    try:
                        unit_price = float(price_str)
                    except ValueError:
                        pass
                break
        for kw in ["品牌:", "品牌："]:
            if kw in body:
                idx = body.find(kw) + len(kw)
                brand = body[idx:idx+30].split("\n")[0].strip()[:30]
                break
        for kw in ["型号:", "型号："]:
            if kw in body:
                idx = body.find(kw) + len(kw)
                model = body[idx:idx+30].split("\n")[0].strip()[:30]
                break

        reply_time = datetime.fromtimestamp(
            m.get("receive_timestamp") or time.time()).strftime("%Y-%m-%d %H:%M:%S")

        # 更新 task 的 replied_supplier_quotes（加 message_id）
        quotes = task.get("replied_supplier_quotes", [])
        if isinstance(quotes, str):
            try:
                quotes = json.loads(quotes)
            except Exception:
                quotes = []
        # 查找是否已有该供应商的报价
        existing = None
        for q in quotes:
            if isinstance(q, dict) and q.get("supplier_name", "") == task.get("_supplier_name", ""):
                existing = q
                break
        quote_obj = {
            "supplier_name": task.get("_supplier_name", ""),
            "email": from_email,
            "brand": brand or "-",
            "model": model or task.get("spare_part_model", ""),
            "unit_price": unit_price,
            "reply_time": reply_time,
            "message_id": msg_id,
        }
        if existing:
            existing.update(quote_obj)
        else:
            quotes.append(quote_obj)

        # 更新 no_reply_supplier
        no_reply = task.get("no_reply_supplier", [])
        if isinstance(no_reply, str):
            try:
                no_reply = json.loads(no_reply)
            except Exception:
                no_reply = []

        tool_table_update(table_key="procurement_task", record_id=task["task_id"], data={
            "replied_supplier_quotes": json.dumps(quotes, ensure_ascii=False),
            "no_reply_supplier": json.dumps(no_reply, ensure_ascii=False),
        })

        # 发飞书卡片（带报价列表 + 选择按钮）
        if config.PROC_FEISHU_PM_OPEN_ID:
            td = dict(task)
            td["replied_supplier_quotes"] = quotes
            td["no_reply_supplier"] = no_reply
            card = _build_proc_card(td, "confirm_purchase_action")
            tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

        results.append({"task_id": task["task_id"], "from_email": from_email,
                        "unit_price": unit_price, "message_id": msg_id})

    return {"skill": "skill-proc-03", "total": len(results), "updates": results,
            "supplier_emails_queried": supplier_emails}


def _skill_proc_04_progress_and_alert() -> dict:
    """定时进度&告警：每小时推送进度，临期 30min 告警，截止超时标记"""
    tasks_r = tool_table_query(table_key="procurement_task",
                               filter={"task_status": "询比价进行中"}, page_size=50)
    if not tasks_r.get("success"):
        return {"skill": "skill-proc-04", "error": tasks_r.get("error")}

    now = int(time.time())
    results = []
    for t in tasks_r.get("records", []):
        task_id = t.get("task_id")
        reply_deadline_str = t.get("reply_deadline", "")
        try:
            dl_dt = datetime.fromisoformat(reply_deadline_str) if reply_deadline_str else None
            remain_sec = int(dl_dt.timestamp() - now) if dl_dt else 0
        except Exception:
            remain_sec = 0

        # 推送进度
        if config.PROC_FEISHU_PM_OPEN_ID:
            replied = json.loads(t.get("replied_supplier_quotes", "[]"))
            no_reply = json.loads(t.get("no_reply_supplier", "[]"))
            total = len(replied) + len(no_reply)
            remain_h = max(0, remain_sec // 3600)
            content = f"""📊询比价进度｜任务ID:{task_id}
总询价供应商：{total}家
已回复：{len(replied)}家｜未回复：{len(no_reply)}家
距离截止还剩：{remain_h}小时"""
            tool_send_feishu_message(config.PROC_FEISHU_PM_OPEN_ID, content)

            # 临期 30min 告警
            if 0 < remain_sec <= 30 * 60:
                no_reply_names = "、".join([s.get("name", "") for s in no_reply])
                tool_send_feishu_message(
                    config.PROC_FEISHU_PM_OPEN_ID,
                    f"⚠️【即将超时告警】询比价任务ID:{task_id}\n距离报价截止仅剩30分钟！\n尚未回复供应商：{no_reply_names}\n请跟进供应商报价。",
                    is_alert=True)

            # 截止超时
            if remain_sec <= 0:
                if no_reply and replied:
                    new_status = "部分供应商超时"
                elif no_reply and not replied:
                    new_status = "全部供应商超时"
                else:
                    new_status = "询比价进行中"  # 全部已回复，保持
                if new_status != "询比价进行中":
                    tool_table_update(table_key="procurement_task", record_id=task_id,
                                      data={"task_status": new_status})
                    timeout_names = "、".join([s.get("name", "") for s in no_reply])
                    tool_send_feishu_message(
                        config.PROC_FEISHU_PM_OPEN_ID,
                        f"🚨询比价已到达截止时间｜任务ID:{task_id}\n超时未回复供应商：{timeout_names}\n请人工评估是否继续选型或重新询价。",
                        is_alert=True)
                else:
                    # 全部已回复，推送收齐通知
                    tool_send_feishu_message(
                        config.PROC_FEISHU_PM_OPEN_ID,
                        f"✅任务ID:{task_id} 全部供应商报价已回复完成，请前往平台完成选型确认。")

        results.append({"task_id": task_id, "remain_sec": remain_sec})

    return {"skill": "skill-proc-04", "checked": len(results), "tasks": results}


def _skill_proc_05_confirm_selection(task: TaskInstance, selected: SupplierItem,
                                     deal_price: float) -> dict:
    """选型确认处理：发采购确认邮件给供应商（reply_to 报价邮件线程）+飞书通知"""
    # 从 replied_supplier_quotes 中查找选中供应商报价邮件的 message_id
    reply_mail_id = None
    quotes = task.replied_supplier_quotes or []
    if isinstance(quotes, str):
        try:
            quotes = json.loads(quotes)
        except Exception:
            quotes = []
    for q in quotes:
        qn = q.get("supplier_name", "") if isinstance(q, dict) else ""
        if qn == selected.name:
            reply_mail_id = q.get("message_id", "")
            break

    subject = f"【采购确认】任务ID:{task.task_id}｜{task.project_name} 备品备件确认采购"
    body = CONFIRM_MAIL_TPL.format(
        project_name=task.project_name, contract_no=task.contract_no,
        spare_part_model=task.spare_part_model, purchase_qty=task.purchase_qty,
        deal_unit_price=deal_price, task_id=task.task_id,
    )
    mail_r = tool_send_mail(to=[selected.email], subject=subject, body_text=body,
                            reply_to_mail_id=reply_mail_id)

    feishu_r = {"success": False, "error": "open_id 未配置"}
    if config.PROC_FEISHU_PM_OPEN_ID:
        card = _build_proc_card(task.dict(), "confirm_purchase", {
            "supplier_name": selected.name, "deal_price": deal_price,
        })
        feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

    return {"skill": "skill-proc-05", "mail": mail_r, "feishu": feishu_r,
            "reply_to": reply_mail_id or "无"}


def _skill_proc_06_parse_delivery_mail(since_ts: int = 0) -> dict:
    """发货信息解析更新：拉取选中供应商邮件，解析发货时间/物流单号"""
    if not since_ts:
        since_ts = int(time.time()) - 3600  # 默认最近 1 小时
    tasks_r = tool_table_query(table_key="procurement_task",
                               filter={"task_status": "已选型确认"}, page_size=50)
    if not tasks_r.get("success"):
        return {"skill": "skill-proc-06", "error": tasks_r.get("error")}

    supplier_emails = []
    task_map = {}  # email → task
    for t in tasks_r.get("records", []):
        sel = json.loads(t.get("selected_supplier", "null") or "null")
        if sel and sel.get("email"):
            supplier_emails.append(sel["email"])
            task_map[sel["email"]] = t

    if not supplier_emails:
        return {"skill": "skill-proc-06", "note": "无待发货任务"}

    mails_r = tool_read_inbox_mail(since_timestamp=since_ts,
                                   filter_sender_email_list=supplier_emails)
    if not mails_r.get("success"):
        return {"skill": "skill-proc-06", "error": mails_r.get("error")}

    results = []
    for m in mails_r.get("mails", []):
        from_email = m.get("from_email", "")
        body = m.get("mail_body_text", "")
        task = task_map.get(from_email)
        if not task:
            continue
        # 简化规则抽取：找"物流单号:XXX"或"运单号:XXX"
        logistics_no = ""
        for kw in ["物流单号:", "物流单号：", "运单号:", "运单号：", "快递单号:", "快递单号："]:
            if kw in body:
                idx = body.find(kw) + len(kw)
                logistics_no = body[idx:idx+30].split()[0] if body[idx:idx+30].split() else body[idx:idx+30].strip()
                logistics_no = logistics_no[:30]
                break
        # 发货时间：用邮件接收时间
        delivery_time = datetime.fromtimestamp(
            m.get("receive_timestamp") or time.time()).strftime("%Y-%m-%d %H:%M:%S")

        if logistics_no:
            tool_table_update(table_key="procurement_task", record_id=task["task_id"],
                              data={"delivery_time": delivery_time,
                                    "logistics_no": logistics_no,
                                    "task_status": "供应商发货中"})
            if config.PROC_FEISHU_PM_OPEN_ID:
                td = dict(task)
                td["delivery_time"] = delivery_time
                td["logistics_no"] = logistics_no
                card = _build_proc_card(td, "delivery")
                tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
            results.append({"task_id": task["task_id"], "logistics_no": logistics_no,
                            "delivery_time": delivery_time})

    return {"skill": "skill-proc-06", "total": len(results), "updates": results}


def _skill_proc_07_input_test_result(task: TaskInstance, test_result: str,
                                     remark: str = "") -> dict:
    """测试结果录入处理：
    通过 → 写台账 + 闭环 + 飞书通知 + 发验收邮件给供应商（reply_to 报价邮件线程）
    失败 → 飞书告警
    """
    if test_result == "通过":
        # 触发 skill-proc-08 写台账
        ledger_r = _skill_proc_08_write_ledger(task)
        # 闭环
        tool_table_update(table_key="procurement_task", record_id=task.task_id,
                          data={"task_status": "流程闭环", "ledger_written": 1})
        # 飞书通知闭环
        feishu_r = {"success": False}
        if config.PROC_FEISHU_PM_OPEN_ID:
            card = _build_proc_card(task.dict(), "ledger_written")
            feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

        # 发验收邮件给供应商（reply_to 报价邮件线程）
        sel = task.selected_supplier
        sel_name = sel.name if sel else ""
        sel_email = sel.email if sel else ""
        # 从 replied_supplier_quotes 查找报价邮件 message_id
        reply_mail_id = None
        quotes = task.replied_supplier_quotes or []
        if isinstance(quotes, str):
            try:
                quotes = json.loads(quotes)
            except Exception:
                quotes = []
        for q in quotes:
            if isinstance(q, dict) and q.get("supplier_name", "") == sel_name:
                reply_mail_id = q.get("message_id", "")
                break

        mail_r = {"success": False, "note": "无供应商邮箱"}
        if sel_email:
            subject = f"【验收通过】任务ID:{task.task_id}｜{task.project_name} 备品备件验收通过"
            body_text = ACCEPTANCE_MAIL_TPL.format(
                project_name=task.project_name, contract_no=task.contract_no,
                spare_part_model=task.spare_part_model, purchase_qty=task.purchase_qty,
                deal_unit_price=task.deal_unit_price or 0, supplier_name=sel_name,
                task_id=task.task_id,
            )
            mail_r = tool_send_mail(to=[sel_email], subject=subject, body_text=body_text,
                                    reply_to_mail_id=reply_mail_id or None)

        return {"skill": "skill-proc-07", "result": "pass", "ledger": ledger_r,
                "feishu": feishu_r, "acceptance_mail": mail_r}
    else:
        feishu_r = {"success": False}
        if config.PROC_FEISHU_PM_OPEN_ID:
            card = _build_proc_card(task.dict(), "test_failed")
            feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
        return {"skill": "skill-proc-07", "result": "fail", "remark": remark, "feishu": feishu_r}


def _skill_proc_08_write_ledger(task: TaskInstance) -> dict:
    """台账写入：从 task 提取字段写入 procurement_ledger 表"""
    if task.task_status == "流程闭环":
        return {"skill": "skill-proc-08", "skipped": True, "note": "task 已闭环，幂等保护跳过"}
    sel = task.selected_supplier.dict() if task.selected_supplier else {}
    ledger_data = {
        "task_id": task.task_id,
        "project_id": task.project_id,
        "project_name": task.project_name,
        "contract_no": task.contract_no,
        "spare_part_model": task.spare_part_model,
        "purchase_qty": task.purchase_qty,
        "selected_supplier_name": sel.get("name", ""),
        "deal_unit_price": task.deal_unit_price,
        "delivery_time": task.delivery_time,
        "logistics_no": task.logistics_no,
        "test_result": task.test_result or "通过",
        "task_close_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "remark": "",
    }
    return tool_table_insert(table_key="procurement_ledger", data=ledger_data)


def _skill_proc_09_cancel_task(task: TaskInstance, cancel_reason: str) -> dict:
    """任务取消处理：contract 工程已 table_update 状态=任务已取消 + cancel_reason，
    neuops 端飞书通知（交互卡片）"""
    feishu_r = {"success": False}
    if config.PROC_FEISHU_PM_OPEN_ID:
        td = task.dict()
        td["cancel_reason"] = cancel_reason
        card = _build_proc_card(td, "task_canceled")
        feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
    return {"skill": "skill-proc-09", "task_id": task.task_id, "feishu": feishu_r}


# ════════════════════════════════════════════════════════════════
# Trigger endpoint（contract 工程调用）
# ════════════════════════════════════════════════════════════════
@router.post("/trigger/task-created")
async def trigger_task_created(task: TaskInstance):
    """contract 工程 create_task 成功后调用：触发 skill-proc-01 + skill-proc-02"""
    r1 = _skill_proc_01_create_task(task)
    r2 = _skill_proc_02_send_inquiry_mail(task)
    return {"success": True, "trigger": "task-created", "task_id": task.task_id,
            "skill_01": r1, "skill_02": r2}


@router.post("/trigger/task-selected")
async def trigger_task_selected(body: SelectionBody):
    """contract 工程选型确认后调用：触发 skill-proc-05"""
    r = _skill_proc_05_confirm_selection(body.task, body.selected_supplier, body.deal_unit_price)
    return {"success": True, "trigger": "task-selected", "task_id": body.task.task_id, "skill_05": r}


@router.post("/trigger/test-result")
async def trigger_test_result(body: TestResultBody):
    """contract 工程录入测试结果后调用：触发 skill-proc-07（内部联动 skill-proc-08）"""
    r = _skill_proc_07_input_test_result(body.task, body.test_result, body.remark)
    return {"success": True, "trigger": "test-result", "task_id": body.task.task_id, "skill_07": r}


@router.post("/trigger/task-canceled")
async def trigger_task_canceled(body: CancelBody):
    """contract 工程取消任务后调用：触发 skill-proc-09"""
    r = _skill_proc_09_cancel_task(body.task, body.cancel_reason)
    return {"success": True, "trigger": "task-canceled", "task_id": body.task.task_id, "skill_09": r}


# ════════════════════════════════════════════════════════════════
# Scheduler tick（定时调度器入口，由外部 systemd timer / asyncio loop 调用）
# ════════════════════════════════════════════════════════════════
@router.post("/scheduler/tick")
async def scheduler_tick(kind: str = "all"):
    """定时调度入口
    kind=quote → skill-proc-03 报价解析（每 5 分钟）
    kind=progress → skill-proc-04 进度告警（每 60 分钟）
    kind=delivery → skill-proc-06 发货解析（每 5 分钟）
    kind=all → 全部依次执行
    """
    results = {}
    if kind in ("quote", "all"):
        results["skill_03"] = _skill_proc_03_parse_quote_mails()
    if kind in ("progress", "all"):
        results["skill_04"] = _skill_proc_04_progress_and_alert()
    if kind in ("delivery", "all"):
        results["skill_06"] = _skill_proc_06_parse_delivery_mail()
    return {"success": True, "kind": kind, "results": results}


# ════════════════════════════════════════════════════════════════
# 健康检查 + 工具列表
# ════════════════════════════════════════════════════════════════
@router.get("/health")
async def health():
    return {
        "success": True,
        "employee": "emp-008",
        "name": "备品备件采购询比价专员",
        "mail_configured": bool(config.PROC_MAIL_PASSWORD),
        "feishu_configured": bool(config.PROC_FEISHU_APP_ID and config.PROC_FEISHU_APP_SECRET),
        "feishu_pm_open_id_configured": bool(config.PROC_FEISHU_PM_OPEN_ID),
        "bitable_configured": bool(config.PROC_FEISHU_BITABLE_APP_TOKEN),
        "db_path": config.PROC_9006_DB_PATH,
    }


@router.get("/tools")
async def list_tools():
    """列出 emp-008 可用的 6 个 MCP 工具"""
    return {
        "success": True,
        "tools": [
            {"name": "read_inbox_mail", "desc": "IMAP 拉取收件箱邮件"},
            {"name": "send_mail", "desc": "SMTP 发送单封邮件"},
            {"name": "batch_send_mail", "desc": "批量发送相同内容邮件"},
            {"name": "send_feishu_message", "desc": "飞书 API 发送文本消息"},
            {"name": "table_query", "desc": "查询 9006 SQLite 表"},
            {"name": "table_insert", "desc": "插入 9006 SQLite 表"},
            {"name": "table_update", "desc": "更新 9006 SQLite 表"},
        ],
    }


# ════════════════════════════════════════════════════════════════
# 测试 endpoint（快速验证工具可用性）
# ════════════════════════════════════════════════════════════════
@router.post("/test/mail")
async def test_mail(body: TestMailBody):
    """快速测试 SMTP 发邮件"""
    r = tool_send_mail(to=body.to, subject=body.subject, body_text=body.body_text)
    return r


@router.post("/test/feishu")
async def test_feishu(body: TestFeishuBody):
    """快速测试飞书消息发送"""
    open_id = body.open_id or config.PROC_FEISHU_PM_OPEN_ID
    r = tool_send_feishu_message(receiver_feishu_open_id=open_id, content=body.content)
    return r


@router.get("/test/table")
async def test_table(table_key: str = "procurement_master_data", page_size: int = 10):
    """快速测试 SQLite 表查询"""
    r = tool_table_query(table_key=table_key, page_size=page_size)
    return r


@router.get("/test/imap")
async def test_imap(since_minutes: int = 60):
    """快速测试 IMAP 收件（拉取最近 N 分钟的邮件）"""
    since_ts = int(time.time()) - since_minutes * 60
    r = tool_read_inbox_mail(since_timestamp=since_ts)
    return r


@router.post("/test/card")
async def test_card(event: str = "task_created"):
    """快速测试飞书交互卡片发送"""
    if not config.PROC_FEISHU_PM_OPEN_ID:
        return {"success": False, "error": "PROC_FEISHU_PM_OPEN_ID 未配置"}
    mock_task = {
        "task_id": "TEST-CARD-001", "project_name": "测试项目", "contract_no": "TEST-CN",
        "spare_part_model": "测试备件", "purchase_qty": 10, "reply_deadline": "2026-08-22 10:00:00",
        "task_status": "询比价进行中", "delivery_time": "", "logistics_no": "",
        "cancel_reason": "",
    }
    extra = {}
    if event == "confirm_purchase":
        extra = {"supplier_name": "测试供应商", "supplier_email": "test@test.com", "deal_price": 1280}
    elif event == "confirm_purchase_action":
        extra = {"supplier_name": "测试供应商", "supplier_email": "test@test.com", "deal_price": 1280}
    card = _build_proc_card(mock_task, event, extra)
    r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
    return {"success": r.get("success", False), "card": card, "send_result": r}


# ════════════════════════════════════════════════════════════════
# 飞书 Card Action Callback（用户在飞书卡片点按钮后触发）
# ════════════════════════════════════════════════════════════════
@router.post("/card-callback")
async def card_callback(request: Request):
    """飞书卡片按钮回调入口
    飞书开放平台 → 应用 → 事件订阅 → 卡片回调 URL 配置为此 endpoint
    用户点「✅ 确认采购」按钮后，飞书 POST 到这里，
    本端解析 action.value 并执行对应业务逻辑（发采购确认邮件+更新 task 状态）。
    """
    body = await request.json()

    # 1. 飞书 URL 验证 challenge（首次配置回调 URL 时飞书发）
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    # 2. 解析 card action
    action_data = body.get("action", {}).get("value", {})
    action = action_data.get("action", "")
    open_id = body.get("open_id", "")

    if action == "confirm_purchase":
        # 飞书内直接确认采购
        return await _handle_confirm_purchase_action(action_data)
    else:
        return {"success": False, "error": f"未知 action: {action}"}


async def _handle_confirm_purchase_action(action_data: dict) -> dict:
    """处理飞书卡片「确认采购」按钮回调
    1. 调 contract 9006 API 更新 task 状态（confirm_selection）
    2. 发采购确认邮件给供应商（reply_to 报价邮件线程）
    3. 返回置灰卡片（替换原卡片，按钮不可再点）
    """
    task_id = action_data.get("task_id", "")
    supplier_name = action_data.get("supplier_name", "")
    supplier_email = action_data.get("supplier_email", "")
    deal_price = action_data.get("deal_price", 0)
    reply_mail_id = action_data.get("reply_mail_id", "")

    if not task_id or not supplier_email:
        return {"success": False, "error": "task_id 或 supplier_email 缺失"}

    # 1. 调 contract 9006 API 确认选型（更新 task 状态 + 操作日志）
    try:
        import httpx
        r = httpx.post(f"http://127.0.0.1:9006/api/procurement/tasks/{task_id}/select",
                       json={"selected_supplier": {"name": supplier_name, "email": supplier_email},
                             "deal_unit_price": float(deal_price)}, timeout=10)
        contract_r = r.json()
        task = contract_r.get("data", {})
    except Exception:
        # 9006 不可用时直接 SQLite 更新
        task_r = tool_table_query(table_key="procurement_task",
                                  filter={"task_id": task_id}, page_size=1)
        records = task_r.get("records", [])
        task = records[0] if records else {}
        tool_table_update(table_key="procurement_task", record_id=task_id, data={
            "task_status": "已选型确认",
            "selected_supplier": json.dumps({"name": supplier_name, "email": supplier_email}),
            "deal_unit_price": deal_price,
        })

    # 2. 发采购确认邮件给供应商（reply_to 报价邮件线程）
    subject = f"【采购确认】任务ID:{task_id}｜{task.get('project_name', '')} 备品备件确认采购"
    body_text = CONFIRM_MAIL_TPL.format(
        project_name=task.get("project_name", ""),
        contract_no=task.get("contract_no", ""),
        spare_part_model=task.get("spare_part_model", ""),
        purchase_qty=task.get("purchase_qty", ""),
        deal_unit_price=deal_price, task_id=task_id,
    )
    mail_r = tool_send_mail(to=[supplier_email], subject=subject, body_text=body_text,
                            reply_to_mail_id=reply_mail_id or None)

    # 3. 返回置灰卡片（替换原卡片，按钮不可再点）
    card = _build_proc_card(task, "purchase_confirmed", {
        "supplier_name": supplier_name, "deal_price": deal_price,
    })
    return {
        "success": True,
        "action": "confirm_purchase",
        "task_id": task_id,
        "mail": mail_r,
        "card": card,  # 飞书会用此卡片替换原卡片
    }

