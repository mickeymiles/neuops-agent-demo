# -*- coding: utf-8 -*-
"""emp-008 备品备件采购询比价智能体 API 路由

三层架构（Skill + Flow + Tool）：
1. Skill（认知层，需要 LLM）：skill-proc-chat(对话编排) / skill-proc-mail-compose(邮件内容组装) / skill-proc-parse(邮件智能解析)
   - 在 seed_data.py 中定义 prompt+tools，由 Agent 对话引擎调度
2. Flow（编排层，不需要 LLM）：_flow_proc_01~09 是确定性流程步骤，由 trigger/scheduler 调用
   - 被 Skill 触发（对话驱动）、被定时器触发（自动轮询）、被 API 触发（页面操作）
3. Tool（原子层，确定性）：send_mail/read_inbox/table_query/procurement_parse_quote 等
   - 任何 Skill、Flow、系统定时器都可调用，无冲突

trigger endpoint 给 contract-compare-9006 工程调用（任务状态变更后触发 Flow 步骤）
scheduler/tick endpoint 给外部定时器调用（systemd timer 或 main.py startup asyncio loop）
"""
import json
import os
import re
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator as pydantic_fieldValidator  # noqa: F401
import pydantic

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
    tool_procurement_query_spare_part,
    tool_procurement_query_contract,
)

router = APIRouter(prefix="/api/procurement-agent", tags=["procurement-agent"])

# 飞书消息卡片构建辅助
PROC_WEB_URL = os.getenv("PROC_WEB_URL", "http://127.0.0.1:9006/procurement")
# 9006 业务 API 基址：读抄送配置走这个
BIZ_9006_BASE = os.getenv("BIZ_9006_BASE", "http://127.0.0.1:9006").rstrip("/")

# 全局抄送列表缓存：减少对 9006 的 HTTP 调用，每 60 秒刷新一次
_GLOBAL_CC_CACHE = {"ts": 0, "cc_list": []}

def _fetch_global_cc_list(*, force: bool = False) -> list:
    """从 9006 /api/procurement/mail-cc/emails 拉取全局抄送邮箱列表，返回纯邮箱字符串列表。
       60 秒缓存；如果 HTTP 失败则返回空列表（不阻断业务邮件），仅打印 warning 日志。
    """
    import time as _t
    now = _t.time()
    if (not force) and _GLOBAL_CC_CACHE["cc_list"] and (now - _GLOBAL_CC_CACHE["ts"] < 60):
        return list(_GLOBAL_CC_CACHE["cc_list"])
    try:
        with httpx.Client(timeout=6) as client:
            r = client.get(f"{BIZ_9006_BASE}/api/procurement/mail-cc/emails")
        r.raise_for_status()
        data = r.json() or {}
        pairs = data.get("cc") or []   # [(name, email), ...]
        cc_emails = []
        for p in pairs:
            if isinstance(p, (list, tuple)) and len(p) >= 2 and p[1]:
                cc_emails.append(str(p[1]).strip())
            elif isinstance(p, str):
                cc_emails.append(p.strip())
        _GLOBAL_CC_CACHE["ts"] = now
        _GLOBAL_CC_CACHE["cc_list"] = cc_emails
        return list(cc_emails)
    except Exception as e:
        # 不阻断邮件发送：仅打印，返回缓存的旧值（若有）
        print(f"[WARN][CC] 拉取全局抄送配置失败: {type(e).__name__}: {e}，返回上次缓存 {_GLOBAL_CC_CACHE['cc_list']}")
        return list(_GLOBAL_CC_CACHE["cc_list"])


# ==============================================================
# 🔧 邮件解析增强（解决供应商只回数字 / 漏关键字 / 物流格式随意的问题）
# ==============================================================

def _clean_mail_body(raw: str) -> str:
    """邮件正文规范化：
    - 合并签名前/引用前截断（On xxx wrote: / -----Original Message-----）
    - 统一全角/半角冒号：全角冒号 -> 半角
    - 连续空行缩成 1 行；去掉 > 引用前缀；去掉 HTML <br> 残余
    """
    if not raw:
        return ""
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    # 去掉每行开头的引用符号
    s = "\n".join(re.sub(r"^[>\s]+", "", ln) for ln in s.split("\n"))
    # 截断：-----Original / On xxx wrote
    s = re.split(r"\n\s*-{5,}\s*(Original|原始|转发|Forwarded)", s, maxsplit=1, flags=re.I)[0]
    s = re.split(r"\n\s*On\s+.+wrote:\s*\n", s, maxsplit=1, flags=re.I)[0]
    # 统一冒号
    s = s.replace("：", ":")
    # 压缩空白
    s = re.sub(r"[ \t\u3000]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# -------- 数字抽取工具 --------
def _extract_amount_candidates(text: str) -> list:
    """从文本中抽取"所有像金额的数字"：
    - 千分位 3,200.00 → 3200.0
    - 货币符 ¥123 / ￥123 / $123
    - 货币字 123元 / 123 RMB / 123块
    返回 list[(float, original_str_span_start)]（有序，保持原文顺序）
    """
    cands = []
    # P1：¥ / ￥ / $ 前缀
    for m in re.finditer(r"[¥￥$]\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", text):
        v = float(m.group(1).replace(",", ""))
        cands.append((v, m.start()))
    # P2：元 / RMB / 块 后缀
    for m in re.finditer(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*(?:元|RMB|rmb|块|圆)", text):
        v = float(m.group(1).replace(",", ""))
        cands.append((v, m.start()))
    # P3：纯数字（单独一行 / 段首段尾 / 有空格包围 / 千分位）—— 放到最后，价格范围后面再过滤
    for m in re.finditer(r"(?:^|[\s，。；、,;])([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)(?=$|[\s，。；、,;\n])", text):
        try:
            v = float(m.group(1).replace(",", ""))
            cands.append((v, m.start()))
        except ValueError:
            pass
    # 按原文顺序去重（同位置的金额只留 1 个）
    seen = set()
    ordered = []
    for v, pos in cands:
        key = (pos, v)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((v, pos))
    ordered.sort(key=lambda x: x[1])
    return [v for v, _ in ordered]


# -------- 报价抽取：6 层策略，从最严格到最兜底 --------
_QUOTE_LABELS = ["单价", "报价", "成交价", "价格", "价钱", "售价"]
_TOTAL_LABELS = ["总价", "合计", "总计", "小计", "总金额", "合计金额", "金额"]
_QTY_LABELS = ["数量", "采购数量", "件数", "台数", "箱数", "个数"]

def robust_parse_supplier_quote(body: str, *,
                                expected_qty: int = None,
                                spare_part_model: str = "",
                                price_range: tuple = (10, 10_000_000)) -> dict:
    """
    6 层加固解析供应商报价邮件：
      P1 结构化关键字（单价: / 总价:）→ 最优先
      P2 货币符号 + 数字（¥3200 / 3,200元）
      P3 乘法三元组匹配（3 × 3200 = 9600）
      P4 金额范围合理的 Top2 数字（最小=单价，最大=总价；唯一则单=总）
      P5 仅一个数字 → 按 expected_qty 反推（数字/qty 合理则是总价，否则是单价）
      P6 兜底：全部没命中 → 全 0，策略="need_manual"，保留 raw 让用户手工录入

    返回 dict：
      {unit_price, total_price, brand, model, lead_time,
       parse_strategy, note, raw_reply_excerpt}
    """
    clean = _clean_mail_body(body)
    excerpt = clean[:600]  # 兜底给前端看的原文片段
    res = {
        "unit_price": 0.0, "total_price": 0.0,
        "brand": "", "model": spare_part_model or "",
        "lead_time": "",
        "parse_strategy": "", "note": "",
        "raw_reply_excerpt": excerpt,
    }

    # --- 品牌/型号（宽松：品牌 / 型号 / 规格） ---
    for label in ["品牌", "厂牌", "生产商", "制造商", "Brand"]:
        m = re.search(rf"{label}\s*[:：]?\s*([^\n，。；、,;]{{2,30}})", clean)
        if m:
            res["brand"] = m.group(1).strip()
            break
    for label in ["型号", "规格型号", "规格", "Model", "Part No", "料号"]:
        m = re.search(rf"{label}\s*[:：]?\s*([^\n，。；、,;]{{2,40}})", clean, flags=re.I)
        if m:
            res["model"] = m.group(1).strip()
            break
    # --- 货期（宽松：N天 / N-N 天 / 次日达 / 当日/今天/明天/后天 / Xxh / 日期字符串） ---
    lead = ""
    # 第一层：标签 + 候选（标签在前 或 "7天交货" 这种货期短语放在标签前的情况都兼容）
    m = re.search(
        r"(?:货期|交货期|交期|约发货|发货(?!日期|时间))\s*[:：约]?\s*([^\s，。；、,;!！?？\n]{2,30})",
        clean,
    )
    if not m:
        # 反过来："7天能发货" / "3-5天交货" —— 货期短语在前，标签在后
        m = re.search(
            r"([^\s，。；、,;!！?？\n]{2,30}?)\s*(?:以内|左右|能)?\s*(?:能发货|能交货|可发货|可交货|交货|发货)",
            clean,
        )
    if m:
        lead = m.group(1).strip("：:，,。.!！?？约略大概")
    if not lead:
        for pat in [
            r"(\d+\s*[-~至到]?\s*\d*\s*天(?:以内|左右)?)\b",
            r"\b(次日达|当日达|当日|今天|明天|后天|现货)\b",
            r"\b(\d+\s*[hH](?:之内|以内|发货)?)\b",
            r"\b(\d{1,2}月\d{1,2}日(?:前)?发货?)\b",
        ]:
            r = re.search(pat, clean)
            if r:
                lead = r.group(1)
                break
    res["lead_time"] = lead or ""

    # --- 报价 6 层策略 ---
    amounts = _extract_amount_candidates(clean)
    min_p, max_p = price_range
    filtered = [a for a in amounts if (min_p <= a <= max_p) and not float(a).is_integer() or (min_p <= int(a) <= max_p)]
    # 如果 filtered 为空（可能是纯数字被价格范围挡了），降级用全量 amounts 再试一次
    candidate_pool = filtered if filtered else amounts

    # P1 结构化关键字：单价 / 报价 / 总价
    for label in _QUOTE_LABELS:
        m = re.search(rf"{label}\s*[:：]\s*([0-9,]{{1,12}}(?:\.[0-9]+)?)", clean)
        if m:
            try:
                res["unit_price"] = float(m.group(1).replace(",", ""))
                res["parse_strategy"] = "P1_keyword_unit"
                break
            except ValueError:
                pass
    for label in _TOTAL_LABELS:
        m = re.search(rf"{label}\s*[:：]\s*([0-9,]{{1,12}}(?:\.[0-9]+)?)", clean)
        if m:
            try:
                res["total_price"] = float(m.group(1).replace(",", ""))
                if not res["parse_strategy"]:
                    res["parse_strategy"] = "P1_keyword_total"
                break
            except ValueError:
                pass
    qty = expected_qty or 0
    for label in _QTY_LABELS:
        m = re.search(rf"{label}\s*[:：]\s*(\d+)", clean)
        if m:
            try:
                qty = int(m.group(1))
                break
            except ValueError:
                pass

    # 若已知单价+数量则补总价；已知总价+数量则补单价（保持一致）
    if qty and res["unit_price"] and not res["total_price"]:
        res["total_price"] = round(res["unit_price"] * qty, 2)
    if qty and res["total_price"] and not res["unit_price"]:
        res["unit_price"] = round(res["total_price"] / qty, 2)

    if res["unit_price"] or res["total_price"]:
        return _finalize_quote(res, qty)

    # P2 货币符号 + 数字（¥3200 / 3,200 元）—— 这一层优先级高，因为"带货币符号肯定是价格"
    for cur in ["¥", "￥", "$", "元", "RMB", "块", "圆"]:
        if cur in clean:
            pool = _extract_amount_candidates(clean)
            if pool:
                vs = sorted(set(pool))
                if len(vs) == 1:
                    v = vs[0]
                    # 单个金额 + 货币符号：供应商最可能报的是单价（除非正文里明确写了"总价/合计..."）
                    total_hint = any(re.search(rf"{lbl}\s*[:：]?\s*{int(v) if float(v).is_integer() else v}", clean) for lbl in _TOTAL_LABELS)
                    if total_hint and qty and (min_p <= v / qty <= max_p):
                        res["total_price"], res["unit_price"] = v, round(v / qty, 2)
                    else:
                        res["unit_price"], res["total_price"] = v, round(v * qty, 2) if qty else v
                    res["parse_strategy"] = "P2_currency_single"
                elif len(vs) >= 2:
                    res["unit_price"], res["total_price"] = vs[0], vs[-1]
                    # 如果"最小 * qty ≈ 最大"，说明判对了；否则如果最大/qty 更合理，则最大是单价
                    if qty and abs(vs[-1] / qty - vs[0]) > 1 and min_p <= vs[-1] / qty <= max_p:
                        res["unit_price"] = round(vs[-1] / qty, 2)
                        res["total_price"] = vs[-1]
                    res["parse_strategy"] = "P2_currency_two"
                return _finalize_quote(res, qty)

    # P3 乘法三元组（3 × 3200 = 9600）
    m = re.search(r"(?:数量|qty|num)?\s*(\d+)\s*(?:[*×xX·]|乘|×)\s*([0-9,]+\.?[0-9]*)\s*(?:=|=|等于)\s*([0-9,]+\.?[0-9]*)", clean)
    if not m:
        m = re.search(r"(\d+)\s*[*×x]\s*([0-9,]+\.?[0-9]*)\s*=\s*([0-9,]+\.?[0-9]*)", clean)
    if m:
        try:
            q3, u3, t3 = int(m.group(1)), float(m.group(2).replace(",", "")), float(m.group(3).replace(",", ""))
            # 交叉验证：qty × unit == total ± 1（四舍五入）
            if abs(q3 * u3 - t3) <= 1:
                res["unit_price"], res["total_price"] = u3, t3
                qty = qty or q3
                res["parse_strategy"] = "P3_mul_triple"
                return _finalize_quote(res, qty)
        except ValueError:
            pass

    # P4 金额范围合理的 Top2（最小=单 最大=总）
    if len(candidate_pool) >= 1:
        vs = sorted(set(candidate_pool))
        if len(vs) == 1:
            v = vs[0]
            # 单数字 + 无关键字/货币：供应商最可能直接报单价（询价邮件一般已经告诉数量）
            # 仅当正文明确写了"总价/合计/总计：v"时，才把这个数字当总价
            total_hint = any(re.search(rf"{lbl}\s*[:：]?\s*{int(v) if float(v).is_integer() else v}", clean) for lbl in _TOTAL_LABELS)
            if total_hint and qty and (min_p <= v / qty <= max_p):
                res["total_price"], res["unit_price"] = v, round(v / qty, 2)
            else:
                res["unit_price"], res["total_price"] = v, round(v * qty, 2) if qty else v
            res["parse_strategy"] = "P4_top1_fallback"
            res["note"] = "⚠️ 邮件仅解析到一个金额数字，已按默认=单价自动推断，建议人工复核"
            return _finalize_quote(res, qty)
        else:
            res["unit_price"], res["total_price"] = vs[0], vs[-1]
            # 合理性：单 * qty 应 ≈ 总（允许 2x 误差，防止是两家报价）
            if qty and not (vs[0] * qty * 0.5 <= vs[-1] <= vs[0] * qty * 2):
                # 可能是两家报价都在邮件里，则取最小当单价，总价要重算
                res["total_price"] = round(res["unit_price"] * qty, 2) if qty else res["unit_price"]
                res["note"] = "⚠️ 邮件里有多个数字，最小被推断为单价，总价已按数量 × 最小算出，请人工复核"
            res["parse_strategy"] = "P4_top2_fallback"
            return _finalize_quote(res, qty)

    # P5 兜底：一个数字都没拿到 → 走 need_manual，前端提示人工录
    res["parse_strategy"] = "P6_need_manual"
    res["note"] = "⚠️ 无法从邮件自动解析报价，请点击铅笔图标手工录入单价 / 总价 / 货期"
    return res


def _finalize_quote(r: dict, qty) -> dict:
    q = qty or 0
    if q and (not r["total_price"] or r["total_price"] == 0) and r["unit_price"]:
        r["total_price"] = round(r["unit_price"] * q, 2)
    if q and (not r["unit_price"] or r["unit_price"] == 0) and r["total_price"]:
        r["unit_price"] = round(r["total_price"] / q, 2)
    # 类型：float
    r["unit_price"] = float(r["unit_price"] or 0.0)
    r["total_price"] = float(r["total_price"] or 0.0)
    return r


# -------- 物流 / 快递单号解析：3 层扫描（8 种载体 + 字母前缀 + 上下文数字） --------
_CARRIER_NAMES = ["顺丰", "顺丰速运", "中通", "圆通", "申通", "韵达", "百世", "德邦", "京东", "EMS", "邮政", "极兔", "天天", "优速", "速尔", "能达", "跨越", "DHL", "UPS", "Fedex", "联邦"]
_CARRIER_PREFIX = ["SF", "JD", "ZT", "YT", "STO", "YD", "JT", "EMS", "DD", "EMS", "DHl", "DHL", "UPS", "FX"]
_LOGI_LABELS = ["物流单号", "快递单号", "运单号", "单号", "快递号", "发货单号", "物流号", "运单编号", "发货单编号", "快递编号", "tracking", "tracking no", "waybill", "waybill no"]

def robust_parse_logistics_info(body: str) -> dict:
    """
    3 层扫描解析物流单号：
      L1 关键字 + 冒号（物流单号：SF123）
      L2 载体名 + 空格/无 + 单号（顺丰 SF123 / 顺丰 1234567890）
      L3 字母前缀 + 纯数字单号直接识别（SF1234567890 / JDVC... / EMS...）
    货期/发货日期也一起抽出来。
    返回 {logistics_no, carrier, delivery_date, raw_excerpt}
    """
    clean = _clean_mail_body(body)
    res = {"logistics_no": "", "carrier": "", "delivery_date": "", "raw_excerpt": clean[:500]}
    # --- L1 关键字 + 冒号/空格 ---
    for label in _LOGI_LABELS:
        m = re.search(rf"{label}\s*[:：]?\s*([A-Za-z0-9]{{6,32}})", clean, flags=re.I)
        if m:
            res["logistics_no"] = m.group(1).strip()
            res["carrier"] = _infer_carrier(res["logistics_no"], clean)
            break
    if not res["logistics_no"]:
        # --- L2 载体名 + 后面的数字/串 ---
        for car in _CARRIER_NAMES:
            if car in clean:
                # 找到载体后面的第一个 6~32 位字母数字串
                idx = clean.index(car)
                tail = clean[idx + len(car): idx + len(car) + 50]
                m = re.search(r"([A-Za-z0-9]{6,32})", tail)
                if m:
                    res["logistics_no"] = m.group(1)
                    res["carrier"] = car
                    break
    if not res["logistics_no"]:
        # --- L3 字母前缀 + 数字（独立单词）---
        # 允许 2-4 字母前缀 + 8-20 数字，或 13 位纯数字（很多民营快递）
        m = re.search(r"\b([A-Z]{2,4}[0-9]{8,20})\b", clean, flags=re.I)
        if m and any(m.group(1).upper().startswith(p) for p in ["SF","JD","ZT","YT","STO","YD","JT","DD","EMS","DHL","UPS","FX","SF"]):
            res["logistics_no"] = m.group(1)
            res["carrier"] = _infer_carrier(res["logistics_no"], clean)
        else:
            m = re.search(r"\b(\d{12,15})\b", clean)
            if m:
                res["logistics_no"] = m.group(1)
                res["carrier"] = _infer_carrier(res["logistics_no"], clean)
    if not res["carrier"]:
        res["carrier"] = _infer_carrier(res.get("logistics_no", ""), clean)

    # --- 发货日期 ---
    # 关键词：发货/发货日期/发货时间/发出/已发/寄出/揽收；日期允许 2026-08-22 / 2026/08/22 / 2026.08.22 / 8月22日
    m = re.search(
        r"(?:发货(?:日期|时间)?|发出|已发|寄出|揽收)\s*(?:时间|日期)?\s*[:：]?\s*"
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{1,2})?|\d{1,2}月\d{1,2}日(?:前)?)",
        clean,
    )
    if m:
        res["delivery_date"] = m.group(1).strip()
    return res


def _infer_carrier(no: str, text: str) -> str:
    """根据单号前缀+正文中出现的载体名推断载体"""
    if not no:
        # 纯文本里出现载体也可以直接返回
        for car in _CARRIER_NAMES:
            if car in text:
                return car
        return ""
    up = no.upper()
    mapping = [
        (["SF"], "顺丰"),
        (["JD"], "京东"),
        (["ZT"], "中通"),
        (["YT"], "圆通"),
        (["STO"], "申通"),
        (["YD"], "韵达"),
        (["JT"], "极兔"),
        (["EMS"], "EMS"),
        (["DHL"], "DHL"),
        (["UPS"], "UPS"),
        (["FX"], "联邦"),
        (["DD"], "德邦"),
    ]
    for prefixes, name in mapping:
        if any(up.startswith(p) for p in prefixes):
            # 文本里也出现了这个载体的名就直接返回
            for alias in _CARRIER_NAMES:
                if alias in text and name in alias:
                    return alias
            return name
    for car in _CARRIER_NAMES:
        if car in text:
            return car
    # 13 位纯数字 = 三通一达多数
    if re.fullmatch(r"\d{13}", no):
        return "民营快递"
    return ""


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
        # ⚠️ schema 2.0 按钮 value 的所有字段必须是字符串，否则 schema 校验 200341
        elements.append({"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": f"✅ 选择 {sn}"},
             "type": "primary", "value": {
                 "action": "confirm_purchase",
                 "task_id": str(tid),
                 "supplier_name": str(sn),
                 "supplier_email": str(em),
                 "deal_price": str(price),
                 "reply_mail_id": str(q.get("message_id", "") or ""),
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
                    f"**承运商：** {task.get('logistics_carrier','') or '-'}\n"
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
    # 可选：资源池供应商的主键 id（前端详情页显示 #id badge 用）
    id: object = None
    # 可选：True=临时供应商（前端详情页显示「临时」badge 用）
    _is_temp: bool = False
    # 可选：发送询价邮件后，回写给该供应商的 RFC Message-ID（报价匹配线程用）
    _sent_msg_id: str = ""
    # 可选：发送询价邮件是否成功（前端详情页显示✅/❌状态用）
    _sent_ok: bool = False
    # 可选：发送失败原因
    _sent_error: str = ""

    # dict() 输出时，None 值 id 字段也保留（避免前端认为这是"没 id 就是临时"的误判）
    model_config = {"extra": "allow"}


class QuoteItem(BaseModel):
    supplier_name: str = ""
    email: str = ""
    brand: str = ""
    model: str = ""
    unit_price: float = 0
    reply_time: str = ""


class TaskInstance(BaseModel):
    """完整 task 实例（contract 工程传过来）

    注意：contract 工程从 SQLite 取出的 task，list/dict 字段可能是 JSON 字符串
    （SQLite 存 TEXT），所以此处用 validator 自动反序列化，避免 422。
    """
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

    @pydantic.field_validator("inquiry_supplier_list", "replied_supplier_quotes",
                             "no_reply_supplier", mode="before")
    @classmethod
    def _parse_list(cls, v):
        if isinstance(v, str) and v:
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []

    @pydantic.field_validator("selected_supplier", mode="before")
    @classmethod
    def _parse_dict(cls, v):
        if isinstance(v, str) and v:
            try:
                return json.loads(v)
            except Exception:
                return None
        if isinstance(v, dict) and not v:
            return None
        return v


class SelectionBody(BaseModel):
    task: TaskInstance
    selected_supplier: SupplierItem
    deal_unit_price: float
    # source 标记：card_callback 表示从飞书卡片按钮触发（此时 flow-proc-05 会跳过「选型确认完成」
    #   飞书新卡片发送，因为 card-callback 会返回一张就地替换的置灰卡片，避免双卡片）
    # web 表示从 9006 前端页面选型（默认，正常发 confirm_purchase 飞书新卡片通知）
    source: str = "web"


class TestResultBody(BaseModel):
    task: TaskInstance
    test_result: str
    remark: str = ""
    source: str = "web"


class CancelBody(BaseModel):
    task: TaskInstance
    cancel_reason: str
    source: str = "web"


class TestMailBody(BaseModel):
    to: List[str]
    subject: str = "智能体测试邮件"
    body_text: str = "这是一封来自 emp-008 智能体的测试邮件。"


class TestFeishuBody(BaseModel):
    open_id: str = ""
    content: str = "emp-008 智能体测试消息"


# ════════════════════════════════════════════════════════════════
# 邮件模板（设计文档第 5 章）
# 【注意】合同名/合同号是内部信息，不发送给供应商（项目经理内部通知/卡片里仍保留）。
# ════════════════════════════════════════════════════════════════
INQUIRY_MAIL_TPL = """您好，请于{reply_deadline}前回复符合以下条件的备件价格
类型：{part_type}
品牌：{part_brand}
型号（PN）：{part_pn}
规格：{part_spec}
成色：{part_condition}
数量：{purchase_qty}"""

CONFIRM_MAIL_TPL = """我司采购如下备件{purchase_qty}个，请于{delivery_deadline}前测试完好后发到如下地址（提供测试报告），寄出请告知单号，谢谢。
部件型号: {spare_part_model}  数量:{purchase_qty}

邮寄地址：
{receiver_address}
收件人：{receiver_name}  联系方式：{receiver_phone}"""

ACCEPTANCE_MAIL_TPL = """您好：

任务ID:{task_id} 备品备件已验收通过。
项目：{project_name}
备件型号：{spare_part_model}
数量：{purchase_qty}
成交单价：{deal_unit_price}
供应商：{supplier_name}

现场工程师已完成硬件测试，结果为通过。
本次采购流程闭环，采购台账已更新。

任务ID：{task_id}
"""


# ════════════════════════════════════════════════════════════════
# Skill 同步桥（认知层入口，调用 LLM 执行 Skill）
# 把 skill-proc-parse 的 prompt 喂给 DeepSeek，带 function calling
# 被 Flow 层同步调用，用 httpx.Client 同步 HTTP，不依赖 asyncio
# ════════════════════════════════════════════════════════════════

# LLM 可选调的解析辅助 Tool schema（OpenAI function calling 格式）
_PARSE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "procurement_parse_quote",
            "description": "正则辅助解析供应商报价邮件,6层策略。标准格式 LLM 可直接提取无需调;长尾/模糊可调此 Tool 作参考",
            "parameters": {
                "type": "object",
                "properties": {
                    "body": {"type": "string", "description": "邮件正文"},
                    "expected_qty": {"type": "integer", "description": "询价数量,用于区分单价/总价"},
                    "spare_part_model": {"type": "string", "description": "备件型号参考"}
                },
                "required": ["body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "procurement_parse_logistics",
            "description": "正则辅助解析物流单号,3层扫描。标准格式 LLM 可直接提取;非标可调此 Tool 作参考",
            "parameters": {
                "type": "object",
                "properties": {
                    "body": {"type": "string", "description": "邮件正文"}
                },
                "required": ["body"]
            }
        }
    }
]


def _exec_parse_tool(name: str, args: dict) -> dict:
    """执行 LLM 调用的解析辅助 Tool"""
    from app.mcp_tools import tool_procurement_parse_quote, tool_procurement_parse_logistics
    if name == "procurement_parse_quote":
        return tool_procurement_parse_quote(**args)
    if name == "procurement_parse_logistics":
        return tool_procurement_parse_logistics(**args)
    return {"error": f"unknown tool {name}"}


def _extract_json_from_llm(text: str) -> dict:
    """从 LLM 文本输出里抽 JSON：兼容 ```json``` 代码块、前后多余文字、首尾 {} 截取"""
    if not text:
        return None
    text = text.strip()
    # 去掉 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        # 兜底：找第一个 { 到最后一个 }
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            try:
                return json.loads(text[first:last + 1])
            except Exception:
                return None
        return None


def _fallback_parse(mail_body: str, parse_mode: str, expected_qty: int,
                    spare_part_model: str, reason: str = "") -> dict:
    """LLM 失败时，降级用原 robust_parse_* 正则函数兜底，保证不比现状差"""
    note_suffix = "｜⚠️ LLM 调用失败,已降级到正则兜底" + (f"({reason})" if reason else "")
    if parse_mode == "logistics":
        r = robust_parse_logistics_info(mail_body)
        return {
            "unit_price": 0.0, "total_price": 0.0, "brand": "", "model": "",
            "lead_time": "",
            "logistics_no": r.get("logistics_no", ""),
            "tracking_no": r.get("logistics_no", ""),
            "carrier": r.get("carrier", ""),
            "delivery_date": r.get("delivery_date", ""),
            "parse_strategy": "fallback_regex",
            "note": note_suffix,
            "raw_reply_excerpt": r.get("raw_excerpt", ""),
            "raw_excerpt": r.get("raw_excerpt", ""),
        }
    r = robust_parse_supplier_quote(mail_body, expected_qty=expected_qty or None,
                                    spare_part_model=spare_part_model)
    return {
        "unit_price": r.get("unit_price", 0.0),
        "total_price": r.get("total_price", 0.0),
        "brand": r.get("brand", ""),
        "model": r.get("model", ""),
        "lead_time": r.get("lead_time", ""),
        "logistics_no": "",
        "tracking_no": "",
        "carrier": "",
        "delivery_date": "",
        "parse_strategy": "fallback_regex",
        "note": (r.get("note", "") or "") + note_suffix,
        "raw_reply_excerpt": r.get("raw_reply_excerpt", ""),
        "raw_excerpt": r.get("raw_reply_excerpt", ""),
    }


def invoke_skill_parse(skill_id: str, mail_body: str, parse_mode: str,
                       expected_qty: int = 0, spare_part_model: str = "") -> dict:
    """同步调用认知 Skill 解析邮件（skill-proc-parse 的同步桥）。

    流程：
      1. 从 seed_data.SKILL_DETAILS 读 prompt
      2. 组装 messages + tools schema，用 httpx.Client(同步) 调 DeepSeek /chat/completions
      3. LLM 可选调 procurement_parse_quote / procurement_parse_logistics Tool，执行后把结果喂回去
      4. 解析 LLM 最终 content 为 JSON，失败 fallback 到 robust_parse_* 兜底

    返回结构对齐两个原函数的并集：
      {unit_price, total_price, brand, model, lead_time,
       logistics_no(=tracking_no), carrier, delivery_date,
       parse_strategy, note, raw_reply_excerpt, raw_excerpt}
    """
    # 读 skill prompt（优先从 JSON 配置文件加载，支持热更新）
    from app.skill_loader import load_skill
    json_skill = load_skill(skill_id)
    if json_skill and json_skill.get("prompt"):
        skill_prompt = json_skill["prompt"]
    else:
        # 降级：从 seed_data 读取
        try:
            from seed_data import SKILL_DETAILS
        except ImportError:
            import sys
            import os
            import importlib.util
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _root not in sys.path:
                sys.path.insert(0, _root)
            try:
                from seed_data import SKILL_DETAILS
            except ImportError:
                _spec = importlib.util.spec_from_file_location(
                    "seed_data", os.path.join(_root, "seed_data.py"))
                _sd = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_sd)
                SKILL_DETAILS = _sd.SKILL_DETAILS

        skill_def = SKILL_DETAILS.get(skill_id)
        skill_prompt = skill_def.get("prompt", "") if skill_def else ""

    if not skill_prompt:
        return _fallback_parse(mail_body, parse_mode, expected_qty, spare_part_model,
                              reason=f"skill {skill_id} 未定义或无 prompt")

    # 复用 agent_chat 的 DeepSeek 配置（key 读取逻辑 + 常量）
    from app.agent_chat import _load_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    key = _load_deepseek_key()
    if not key:
        return _fallback_parse(mail_body, parse_mode, expected_qty, spare_part_model,
                              reason="DeepSeek API Key 未配置")

    messages = [
        {"role": "system", "content": skill_prompt},
        {"role": "user", "content": (
            f"parse_mode={parse_mode}\n"
            f"expected_qty={expected_qty}\n"
            f"spare_part_model={spare_part_model}\n"
            f"mail_body:\n{mail_body}"
        )},
    ]
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
        "tools": _PARSE_TOOLS_SCHEMA,
        "tool_choice": "auto",
    }

    final_json = None
    try:
        with httpx.Client(timeout=180) as client:
            # 最多 2 轮：第 1 轮 LLM 可能调 Tool，第 2 轮 LLM 输出最终 JSON
            for round_no in range(2):
                r = client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
                if r.status_code != 200:
                    return _fallback_parse(mail_body, parse_mode, expected_qty,
                                          spare_part_model,
                                          reason=f"DeepSeek HTTP {r.status_code}")
                data = r.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message", {}) or {}

                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    # 把 LLM 的 tool_calls 消息追加到对话，再执行 Tool 喂回去
                    payload["messages"].append(msg)
                    for tc in tool_calls:
                        fn = tc.get("function", {}) or {}
                        tname = fn.get("name", "")
                        try:
                            targs = json.loads(fn.get("arguments", "{}"))
                        except Exception:
                            targs = {}
                        tresult = _exec_parse_tool(tname, targs)
                        payload["messages"].append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tname,
                            "content": json.dumps(tresult, ensure_ascii=False),
                        })
                    continue  # 让 LLM 出最终 JSON
                # 无 tool_calls，content 应该是最终 JSON
                final_json = _extract_json_from_llm(msg.get("content", "") or "")
                break
    except Exception as e:
        return _fallback_parse(mail_body, parse_mode, expected_qty, spare_part_model,
                              reason=f"调用异常 {e}")

    if not final_json:
        return _fallback_parse(mail_body, parse_mode, expected_qty, spare_part_model,
                              reason="LLM 输出 JSON 解析失败")

    # 字段映射：LLM 输出 tracking_no，Flow 层（_flow_proc_06）取 logistics_no
    return {
        "unit_price": float(final_json.get("unit_price") or 0.0),
        "total_price": float(final_json.get("total_price") or 0.0),
        "brand": final_json.get("brand") or "",
        "model": final_json.get("model") or spare_part_model or "",
        "lead_time": final_json.get("lead_time") or "",
        "logistics_no": final_json.get("tracking_no") or "",
        "tracking_no": final_json.get("tracking_no") or "",  # 双键，兼容两个原函数字段名
        "carrier": final_json.get("carrier") or "",
        "delivery_date": final_json.get("delivery_date") or "",
        "parse_strategy": final_json.get("parse_strategy") or "llm_direct",
        "note": final_json.get("note") or "",
        "raw_reply_excerpt": final_json.get("raw_reply_excerpt") or mail_body[:300],
        "raw_excerpt": final_json.get("raw_reply_excerpt") or mail_body[:500],
    }


def _fallback_mail(mail_type: str, context: dict, reason: str = "") -> dict:
    """LLM 邮件组装失败时，降级用硬编码模板兜底，保证不比现状差"""
    suffix = f"\n\n[邮件由模板兜底生成，原因：{reason}]" if reason else ""
    if mail_type == "inquiry":
        contract_no = context.get("contract_no", "")
        contract_name = context.get("contract_name", "") or context.get("project_name", "")
        spare_part_model = context.get("spare_part_model", "")
        subject = (f"{contract_no}（{contract_name}）-{spare_part_model}型号备件询价邮件"
                   if contract_no else
                   f"【备品备件询价】{contract_name}｜任务ID:{context.get('task_id','')}")
        body = INQUIRY_MAIL_TPL.format(
            reply_deadline=context.get("reply_deadline", ""),
            part_type=context.get("part_type", ""),
            part_brand=context.get("part_brand", ""),
            part_pn=context.get("part_pn", "") or spare_part_model,
            part_spec=context.get("part_spec", ""),
            part_condition=context.get("part_condition", ""),
            purchase_qty=context.get("purchase_qty", ""),
        ) + suffix
    elif mail_type == "confirm":
        subject = f"【采购确认】任务ID:{context.get('task_id','')}｜{context.get('contract_name','')} {context.get('spare_part_model','')} 备品备件确认采购"
        body = CONFIRM_MAIL_TPL.format(
            purchase_qty=context.get("purchase_qty", ""),
            delivery_deadline=context.get("delivery_deadline", ""),
            spare_part_model=context.get("spare_part_model", ""),
            receiver_address=context.get("receiver_address", ""),
            receiver_name=context.get("receiver_name", ""),
            receiver_phone=context.get("receiver_phone", ""),
        ) + suffix
    elif mail_type == "acceptance":
        subject = f"【验收通过】任务ID:{context.get('task_id','')}｜{context.get('project_name','')} 备品备件验收通过"
        body = ACCEPTANCE_MAIL_TPL.format(
            project_name=context.get("project_name", ""),
            contract_no=context.get("contract_no", ""),
            spare_part_model=context.get("spare_part_model", ""),
            purchase_qty=context.get("purchase_qty", ""),
            deal_unit_price=context.get("deal_unit_price", 0),
            supplier_name=context.get("supplier_name", ""),
            task_id=context.get("task_id", ""),
        ) + suffix
    else:
        subject = f"【采购通知】任务ID:{context.get('task_id','')}"
        body = f"任务ID:{context.get('task_id','')}\n\n邮件由模板兜底生成。{suffix}"
    return {"subject": subject, "body_text": body, "composed_by": "template_fallback"}


def invoke_skill_mail_compose(mail_type: str, context: dict) -> dict:
    """同步调用认知 Skill 组装邮件内容（skill-proc-mail-compose 的同步桥）。

    流程：
      1. 从 seed_data.SKILL_DETAILS 读 skill-proc-mail-compose prompt
      2. 组装 messages，用 httpx.Client(同步) 调 DeepSeek /chat/completions
      3. LLM 直接输出 {subject, body_text} JSON
      4. 失败 fallback 到硬编码模板兜底

    Args:
        mail_type: "inquiry"(询价) / "confirm"(采购确认) / "acceptance"(验收通知)
        context: 邮件上下文字段字典，按 mail_type 不同而不同
            - inquiry:   {project_name, spare_part_model, purchase_qty, reply_deadline, task_id}
            - confirm:   {project_name, contract_no, spare_part_model, purchase_qty, deal_unit_price, task_id, supplier_name}
            - acceptance:{project_name, contract_no, spare_part_model, purchase_qty, deal_unit_price, supplier_name, task_id}

    Returns:
        {"subject": str, "body_text": str, "composed_by": "llm"|"template_fallback"}
    """
    # 读 skill prompt（优先从 JSON 配置文件加载，支持热更新）
    from app.skill_loader import load_skill
    json_skill = load_skill("skill-proc-mail-compose")
    if json_skill and json_skill.get("prompt"):
        skill_prompt = json_skill["prompt"]
    else:
        # 降级：从 seed_data 读取
        try:
            from seed_data import SKILL_DETAILS
        except ImportError:
            import sys
            import os
            import importlib.util
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _root not in sys.path:
                sys.path.insert(0, _root)
            try:
                from seed_data import SKILL_DETAILS
            except ImportError:
                _spec = importlib.util.spec_from_file_location(
                    "seed_data", os.path.join(_root, "seed_data.py"))
                _sd = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_sd)
                SKILL_DETAILS = _sd.SKILL_DETAILS

        skill_def = SKILL_DETAILS.get("skill-proc-mail-compose")
        skill_prompt = skill_def.get("prompt", "") if skill_def else ""

    if not skill_prompt:
        return _fallback_mail(mail_type, context, "skill-proc-mail-compose 未定义或无 prompt")

    # 读 API key
    from app.agent_chat import _load_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    key = _load_deepseek_key()
    if not key:
        return _fallback_mail(mail_type, context, "DeepSeek API Key 未配置")

    # 组装 context 文本喂给 LLM
    context_lines = [f"mail_type={mail_type}"]
    for k, v in context.items():
        context_lines.append(f"{k}={v}")

    # system prompt + 邮件组装的输出格式强制约束
    system_prompt = skill_prompt + (
        "\n\n【输出格式强制要求】你必须返回纯 JSON（无 markdown 代码块标记、无解释文字、无问候语）："
        '\n{"subject": "邮件主题", "body_text": "邮件正文全文"}'
        "\n不要输出 JSON 以外的任何内容。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(context_lines)},
    ]
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,  # 邮件措辞需要一点创造性
        "max_tokens": 2000,
    }

    final_json = None
    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code != 200:
                return _fallback_mail(mail_type, context, f"DeepSeek HTTP {r.status_code}")
            data = r.json()
            content = ((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")
            final_json = _extract_json_from_llm(content)
    except Exception as e:
        return _fallback_mail(mail_type, context, f"调用异常 {e}")

    if not final_json or not final_json.get("subject") or not final_json.get("body_text"):
        return _fallback_mail(mail_type, context, "LLM 输出 JSON 解析失败或字段缺失")

    return {
        "subject": str(final_json["subject"]).strip(),
        "body_text": str(final_json["body_text"]).strip(),
        "composed_by": "llm",
    }


# ════════════════════════════════════════════════════════════════
# Flow 步骤函数（确定性流程编排，不需要 LLM）
# 被 trigger endpoint / scheduler tick / card callback 调用
# 对应 Skill 层的 skill-proc-chat 在对话中触发这些 Flow 步骤
# ════════════════════════════════════════════════════════════════
def _flow_proc_01_create_task(task: TaskInstance) -> dict:
    """创建询比价任务：contract 工程已完成 create_task 落库，neuops 端不需要重写，
    仅返回 task 实例给 flow-proc-02 使用。"""
    return {"flow": "flow-proc-01", "task_id": task.task_id, "status": "created", "task": task.dict()}


def _lookup_contract(contract_no: str) -> dict:
    """按合同编号查合同详情（含收件人/联系方式/邮寄地址），查不到返回空。"""
    if not contract_no:
        return {}
    try:
        r = tool_procurement_query_contract(keyword=str(contract_no).strip())
        recs = r.get("records") or []
        for c in recs:
            if (c.get("contract_no") or "").strip() == str(contract_no).strip():
                return c
        return recs[0] if recs else {}
    except Exception:
        return {}


def _lookup_spare_attrs(model: str) -> dict:
    """按型号/编码/名称反查备件主数据，取 类型/品牌/型号PN/规格/成色。"""
    if not model:
        return {}
    try:
        r = tool_procurement_query_spare_part(keyword=str(model).strip())
        recs = r.get("records") or []
        for p in recs:
            if (p.get("part_code") or "").strip() == str(model).strip():
                return p
        if recs:
            return recs[0]
        return {}
    except Exception:
        return {}


def _build_inquiry_ctx(task: TaskInstance) -> dict:
    """询价邮件上下文：补 合同号/合同名 + 备件属性（类型/品牌/PN/规格/成色）。"""
    contract = _lookup_contract(task.contract_no)
    part = _lookup_spare_attrs(task.spare_part_model)
    return {
        "contract_no": task.contract_no,
        "contract_name": (contract.get("contract_name") or task.project_name or ""),
        "project_name": (contract.get("contract_name") or task.project_name or ""),
        "spare_part_model": task.spare_part_model,
        "part_type": part.get("category", ""),
        "part_brand": part.get("brand", ""),
        "part_pn": part.get("part_code", "") or task.spare_part_model,
        "part_spec": part.get("spec_model", ""),
        "part_condition": part.get("condition", ""),
        "purchase_qty": task.purchase_qty,
        "reply_deadline": task.reply_deadline,
        "task_id": task.task_id,
    }


def _build_confirm_ctx(task: TaskInstance, deal_price: float, supplier_name: str) -> dict:
    """采购确认邮件上下文：补 合同收件人/联系方式/邮寄地址 等。"""
    contract = _lookup_contract(task.contract_no)
    return {
        "contract_no": task.contract_no,
        "contract_name": (contract.get("contract_name") or task.project_name or ""),
        "project_name": (contract.get("contract_name") or task.project_name or ""),
        "spare_part_model": task.spare_part_model,
        "purchase_qty": task.purchase_qty,
        "deal_unit_price": deal_price,
        "delivery_deadline": "",
        "receiver_name": contract.get("receiver_name", ""),
        "receiver_phone": contract.get("receiver_phone", ""),
        "receiver_address": contract.get("receiver_address", ""),
        "task_id": task.task_id,
        "supplier_name": supplier_name,
    }


def _flow_proc_02_send_inquiry_mail(task: TaskInstance) -> dict:
    """LLM 组装&发送询价邮件 + 飞书通知项目经理任务已发起
    邮件组装由 skill-proc-mail-compose（LLM）完成，失败时自动降级到硬编码模板
    【修复】发送后给 inquiry_supplier_list 每一项回写 _sent_msg_id，用于 flow-03 按
    In-Reply-To/References 匹配供应商回复，避免 1 个供应商邮箱对应多个任务时串任务。
    """
    ctx = _build_inquiry_ctx(task)
    mail_content = invoke_skill_mail_compose("inquiry", ctx)
    subject = mail_content["subject"]
    body = mail_content["body_text"]

    # —— 预标记：资源池(id 存在) vs 临时供应商(id 不存在) ——
    inq_list = list(task.inquiry_supplier_list or [])
    for s in inq_list:
        try:
            s._is_temp = bool(not s.id)
        except Exception:
            # Pydantic v1 protected namespace 不允许直接赋值 _xxx → fallback model_extra
            try:
                if not hasattr(s, "__pydantic_extra__") or s.__pydantic_extra__ is None:
                    s.__pydantic_extra__ = {}
                s.__pydantic_extra__["_is_temp"] = bool(not getattr(s, "id", None))
            except Exception:
                pass

    to_list = [s.email for s in inq_list]
    global_cc = _fetch_global_cc_list()
    mail_r = tool_batch_send_mail(receiver_email_list=to_list, subject=subject, body_text=body,
                                  cc=global_cc)
    mail_r["global_cc"] = global_cc
    mail_r["composed_by"] = mail_content.get("composed_by", "llm")

    # —— 按 email 匹配，回写每封询价邮件的 message_id + 状态 ——
    sent_map: dict[str, dict] = {}
    for s in mail_r.get("sent") or []:
        sent_map[str(s.get("email", "")).lower()] = s
    for s in inq_list:
        key = str(s.email or "").lower()
        sd = sent_map.get(key) or {}
        ok_bool = bool(sd and sd.get("message_id"))
        msg_id = str(sd.get("message_id") or "")
        try:
            s._sent_msg_id = msg_id
            s._sent_ok = ok_bool
            if not ok_bool:
                failed = [f for f in (mail_r.get("fail_email_list") or []) if str(f.get("email", "")).lower() == key]
                s._sent_error = (failed[0].get("error") if failed else "") or (
                    "" if ok_bool else "系统错误：未返回邮件 ID")
        except Exception:
            try:
                if not hasattr(s, "__pydantic_extra__") or s.__pydantic_extra__ is None:
                    s.__pydantic_extra__ = {}
                s.__pydantic_extra__["_sent_msg_id"] = msg_id
                s.__pydantic_extra__["_sent_ok"] = ok_bool
            except Exception:
                pass

    # —— 回写到 9006 procurement_task.inquiry_supplier_list（DB 持久化，前端详情页展示 + flow-03 读取）——
    try:
        # model_dump() 兼容 Pydantic v2；失败退回 .dict()
        try:
            serial = [s.model_dump() for s in inq_list]
        except Exception:
            serial = [s.dict() for s in inq_list]
        # Pydantic 会过滤 _ 开头字段为 private，强制再合并一次
        for s_obj, s_raw in zip(inq_list, serial):
            for priv_key in ("_is_temp", "_sent_msg_id", "_sent_ok", "_sent_error"):
                if priv_key not in s_raw:
                    try:
                        v = getattr(s_obj, priv_key, None)
                    except Exception:
                        v = (getattr(s_obj, "__pydantic_extra__", None) or {}).get(priv_key)
                    s_raw[priv_key] = v
        upd = tool_table_update(table_key="procurement_task",
                                record_id=task.task_id,
                                data={"inquiry_supplier_list": json.dumps(serial, ensure_ascii=False),
                                      "no_reply_supplier": json.dumps(serial, ensure_ascii=False)})
        mail_r["persist_supplier_status"] = {"success": bool(upd.get("success")),
                                              "error": upd.get("error") if not upd.get("success") else ""}
    except Exception as e:
        mail_r["persist_supplier_status"] = {"success": False, "error": f"{type(e).__name__}: {e}"}

    # 同步 task 对象（供后续 Pydantic 再引用时使用）
    task.inquiry_supplier_list = inq_list

    # 飞书通知项目经理任务已发起（交互卡片）
    feishu_r = {"success": False, "error": "open_id 未配置"}
    if config.PROC_FEISHU_PM_OPEN_ID:
        card = _build_proc_card(task.dict(), "task_created")
        feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

    return {"flow": "flow-proc-02", "mail": mail_r, "feishu": feishu_r,
            "composed_by": mail_content.get("composed_by", "llm"),
            "suppliers_sent": sum(1 for s in inq_list if getattr(s, "_sent_ok", False)),
            "suppliers_total": len(inq_list)}


def _flow_proc_03_parse_quote_mails(since_ts: int = 0) -> dict:
    """邮件报价解析监听：拉取供应商邮件，LLM 解析报价回填 task。
    调 skill-proc-parse（LLM 可选调 procurement_parse_quote 正则 Tool 作辅助）；
    LLM 失败时 invoke_skill_parse 内部会 fallback 到 robust_parse_supplier_quote 兜底。

    修复（2026-08-24）：
    - 修复「同一供应商邮箱出现在多个任务中导致报价串任务」：
      task_map 改为 email → 多个任务；并从询价邮件记录中回写到 inquiry_supplier_list 的
      _sent_msg_id（见 flow-02），用于 In-Reply-To / References 精准命中唯一条目。
    - 修复「临时供应商有回复但步骤2看不到」：匹配时按 email 对任务的 inquiry 列表做
      1:N 遍历，不依赖 supplier_name 相等（临时供应商名字可能与邮件发件人显示不一致）。
    - 过滤假回复（采购方自己的询价函副本）：
      tool_read_inbox_mail 黑名单 + 正文询价关键字双重过滤，根本不会返回。
    """
    if not since_ts:
        # 【修复 2026-08-27】此前默认只扫最近 10 分钟，若某次调度因服务重启/中断而错过，
        # 供应商稍早到达的回复会被 since 窗口直接跳过且永不补扫 → 前端一直看不到回复。
        # 放大到最近 2 小时并用 message_id 去重（见下方 quotes_before 判重），安全补抓不重复。
        since_ts = int(time.time()) - 7200

    tasks_r = tool_table_query(table_key="procurement_task",
                               filter={"task_status": "询比价进行中"}, page_size=50)
    all_tasks = list(tasks_r.get("records", [])) if tasks_r.get("success") else []

    supplier_emails: set = set()
    email_tasks_map: dict[str, list] = {}  # email_lower -> list of (task_dict, supplier_dict)
    msgid_supplier_map: dict[str, tuple] = {}  # norm_msg_id -> (task_dict, supplier_dict)

    def _norm_mid(m):
        if not m: return ""
        s = str(m).strip()
        while s.startswith("<"): s = s[1:]
        while s.endswith(">"): s = s[:-1]
        return s.strip()

    for t in all_tasks:
        try:
            inq = json.loads(t.get("inquiry_supplier_list", "[]"))
        except Exception:
            inq = []
        if not isinstance(inq, list):
            inq = []
        for s in inq:
            if not isinstance(s, dict) or not s.get("email"):
                continue
            em_key = str(s["email"]).lower().strip()
            supplier_emails.add(em_key)
            email_tasks_map.setdefault(em_key, []).append((dict(t), s))
            sent_mid = _norm_mid(s.get("_sent_msg_id") or s.get("sent_msg_id") or "")
            if sent_mid and sent_mid not in msgid_supplier_map:
                msgid_supplier_map[sent_mid] = (dict(t), s)

    supplier_emails_list = sorted(supplier_emails)
    if not supplier_emails_list:
        return {"flow": "flow-proc-03", "mails": [], "note": "无进行中任务，跳过"}

    known_inquiry_msg_ids = sorted(msgid_supplier_map.keys()) if msgid_supplier_map else None
    mails_r = tool_read_inbox_mail(
        since_timestamp=since_ts,
        filter_sender_email_list=supplier_emails_list,
        match_in_reply_to_msg_ids=known_inquiry_msg_ids,
    )
    if not mails_r.get("success"):
        return {"flow": "flow-proc-03", "error": mails_r.get("error"), "mails": []}

    results = []
    for m in mails_r.get("mails", []):
        from_email = m.get("from_email", "")
        body = m.get("mail_body_text", "")
        msg_id = m.get("message_id", "")
        in_reply_to = m.get("in_reply_to", "") or ""
        references = m.get("references", "") or ""
        from_key = str(from_email).lower().strip()

        chosen_task = None
        chosen_supplier = None
        match_reason = ""
        if known_inquiry_msg_ids:
            hit_threads = set()
            for raw_ref in [in_reply_to, references]:
                if raw_ref:
                    for part in re.split(r"\s+", str(raw_ref).strip()):
                        n = _norm_mid(part)
                        if n and n in msgid_supplier_map:
                            hit_threads.add(n)
            if hit_threads:
                for h in hit_threads:
                    tt, ss = msgid_supplier_map[h]
                    if str(ss.get("email", "")).lower() == from_key:
                        chosen_task, chosen_supplier = dict(tt), dict(ss)
                        match_reason = f"thread msg_id hit {h}"
                        break
                # 【修复 2026-08-24】线程命中但邮箱不一致时，不再直接丢弃并 continue，
                # 而是留给下方 email fallback 再匹配一次。
                # 背景：供应商 A 收到的询价邮件被内部转发给同任务的临时供应商 B，B 点"回复"
                # 后，In-Reply-To 指向发给 A 的询价 msg_id（线程对应 A 的登记条目），
                # 但实际发件人是 B（也是该任务合法登记的供应商）。原来的 continue 会导致
                # B 的真实报价回复被直接丢弃，步骤 2 看不到。改为走 email fallback 后，
                # B 能按邮箱匹配到该任务，从而正确回填报价。
                if chosen_task is None:
                    match_reason = (
                        f"thread_hit_but_email_mismatch_fallback"
                        f"(thread_hit_count={len(hit_threads)})"
                    )

        if chosen_task is None:
            cands = email_tasks_map.get(from_key) or []
            if not cands:
                continue
            cands_sorted = sorted(
                cands,
                key=lambda x: (x[0].get("create_time") or "", x[0].get("task_id") or ""),
                reverse=True,
            )
            chosen_task, chosen_supplier = dict(cands_sorted[0][0]), dict(cands_sorted[0][1])
            match_reason = f"email fallback (candidates={len(cands)} picked newest {chosen_task.get('task_id')})"

        task = chosen_task
        supplier_name = (chosen_supplier or {}).get("name") or task.get("_supplier_name") or ""

        quotes_before = task.get("replied_supplier_quotes", [])
        if isinstance(quotes_before, str):
            try:
                quotes_before = json.loads(quotes_before)
            except Exception:
                quotes_before = []
        if msg_id and any((q.get("message_id") == msg_id) for q in quotes_before if isinstance(q, dict)):
            results.append({"task_id": task["task_id"], "from_email": from_email,
                            "message_id": msg_id, "skipped": True,
                            "reason": "报价邮件已处理过，跳过重复更新+重复卡片",
                            "match_reason": match_reason})
            continue

        expected_qty = task.get("purchase_qty") or 1
        try:
            expected_qty = int(expected_qty)
        except (ValueError, TypeError):
            expected_qty = 1
        pq = invoke_skill_parse(
            "skill-proc-parse",
            mail_body=body,
            parse_mode="quote",
            expected_qty=expected_qty,
            spare_part_model=task.get("spare_part_model", ""),
        )
        unit_price = pq["unit_price"]
        total_price = pq["total_price"]
        brand = pq["brand"]
        model = pq["model"]
        lead_time = pq["lead_time"]
        parse_strategy = pq["parse_strategy"]
        parse_note = pq["note"]
        raw_reply_excerpt = pq["raw_reply_excerpt"]

        reply_time = datetime.fromtimestamp(
            m.get("receive_timestamp") or time.time()).strftime("%Y-%m-%d %H:%M:%S")

        quotes = list(quotes_before)
        existing = None
        for q in quotes:
            if isinstance(q, dict) and str(q.get("email", "")).lower() == from_key:
                existing = q
                break
        if existing and existing.get("is_manual"):
            parse_note = (parse_note or "") + "｜⚠️ 本条已人工录入，自动解析未覆盖原值"
            existing["reply_time"] = reply_time
            existing["message_id"] = msg_id
            existing["raw_reply_excerpt"] = raw_reply_excerpt
            quote_obj = None
        else:
            quote_obj = {
                "supplier_name": supplier_name,
                "email": from_email,
                "brand": brand or "-",
                "model": model or task.get("spare_part_model", ""),
                "unit_price": unit_price,
                "total_price": total_price or round((unit_price or 0.0) * expected_qty, 2),
                "lead_time": lead_time or "",
                "reply_time": reply_time,
                "message_id": msg_id,
                "parse_strategy": parse_strategy or "",
                "parse_note": parse_note or "",
                "raw_reply_excerpt": raw_reply_excerpt,
                "is_manual": False,
                "_inquiry_sent_msg_id": (chosen_supplier or {}).get("_sent_msg_id", ""),
                "_match_reason": match_reason,
            }
            if existing:
                existing.update(quote_obj)
            else:
                quotes.append(quote_obj)

        no_reply = task.get("no_reply_supplier", [])
        if isinstance(no_reply, str):
            try:
                no_reply = json.loads(no_reply)
            except Exception:
                no_reply = []
        no_reply = [s for s in no_reply
                    if isinstance(s, dict)
                    and str(s.get("email", "")).lower() != from_key]

        tool_table_update(table_key="procurement_task", record_id=task["task_id"], data={
            "replied_supplier_quotes": json.dumps(quotes, ensure_ascii=False),
            "no_reply_supplier": json.dumps(no_reply, ensure_ascii=False),
        })

        if config.PROC_FEISHU_PM_OPEN_ID:
            td = dict(task)
            td["replied_supplier_quotes"] = quotes
            td["no_reply_supplier"] = no_reply
            inquiry_list = td.get("inquiry_supplier_list", [])
            if isinstance(inquiry_list, str):
                try:
                    inquiry_list = json.loads(inquiry_list)
                except Exception:
                    inquiry_list = []
            total_cnt = max(len(inquiry_list) or 1, len(quotes) + len(no_reply))
            new_quote_note = f"收到新报价：{supplier_name} ¥{unit_price}（还剩{len(no_reply)}家未回复）"
            if len(quotes) >= total_cnt and len(no_reply) == 0:
                new_quote_note = f"✅全部供应商已报价，请选型（共{total_cnt}家）"
            card = _build_proc_card(td, "confirm_purchase_action", {"_note": new_quote_note})
            tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

        results.append({"task_id": task["task_id"], "from_email": from_email,
                        "unit_price": unit_price, "message_id": msg_id,
                        "is_new_quote": True, "supplier_name": supplier_name,
                        "match_reason": match_reason})

    return {"flow": "flow-proc-03", "total": len(results),
            "new_quotes": sum(1 for r in results if r.get("is_new_quote")),
            "skipped_duplicates": sum(1 for r in results if r.get("skipped")),
            "updates": results,
            "supplier_emails_queried": supplier_emails_list,
            "thread_match_count": len(msgid_supplier_map),
            "email_multi_task_count": sum(1 for v in email_tasks_map.values() if len(v) > 1)}



def _flow_proc_04_progress_and_alert() -> dict:
    """定时告警 & 状态变化通知（只在「有新事件」时发送飞书，避免每小时刷一模一样的进度）

    触发飞书消息的事件（每个事件/每个任务只发 1 次）：
      1. 距离报价截止 <=30 分钟且之前没发过「临期告警」 → 发 1 次 ⚠️ 即将超时告警
      2. 已到达截止时间：
         - 有未回复供应商 → 更新 task_status 到 部分/全部超时 + 发 🚨 超时告警 1 次
         - 全部已报价，且之前没发过「报价齐提醒」 → 发 ✅ 全部已报价 1 次
    """
    tasks_r = tool_table_query(table_key="procurement_task",
                               filter={"task_status": "询比价进行中"}, page_size=50)
    if not tasks_r.get("success"):
        return {"flow": "flow-proc-04", "error": tasks_r.get("error")}

    now = int(time.time())
    results = []
    for t in tasks_r.get("records", []):
        task_id = t.get("task_id")
        reply_deadline_str = t.get("reply_deadline", "")
        # 读取 DB 中保存的"已发送事件"标记，格式：{"warned_30min": 1, "notified_all_replied": 1, "notified_timeout": 1}
        notify_marker_raw = t.get("_notify_markers") or t.get("notify_markers") or "{}"
        notify_markers = {}
        if isinstance(notify_marker_raw, str) and notify_marker_raw:
            try:
                notify_markers = json.loads(notify_marker_raw)
            except Exception:
                notify_markers = {}
        if not isinstance(notify_markers, dict):
            notify_markers = {}

        try:
            dl_dt = datetime.fromisoformat(reply_deadline_str) if reply_deadline_str else None
            remain_sec = int(dl_dt.timestamp() - now) if dl_dt else 0
        except Exception:
            remain_sec = 0

        replied = json.loads(t.get("replied_supplier_quotes", "[]") or "[]")
        no_reply = json.loads(t.get("no_reply_supplier", "[]") or "[]")
        inquiry_list = json.loads(t.get("inquiry_supplier_list", "[]") or "[]")
        total_cnt = max(len(inquiry_list) or 1, len(replied) + len(no_reply))

        sent_events = []  # 本次发送了哪些事件，用于写回 marker
        extra_update = {}

        if config.PROC_FEISHU_PM_OPEN_ID:
            # (1) 临期 30min 告警：每个任务只发 1 次
            if 0 < remain_sec <= 30 * 60 and not notify_markers.get("warned_30min"):
                no_reply_names = "、".join([s.get("name", "") for s in no_reply]) or "无"
                tool_send_feishu_message(
                    config.PROC_FEISHU_PM_OPEN_ID,
                    f"⚠️【即将超时告警】询比价任务ID:{task_id}\n"
                    f"距离报价截止仅剩30分钟！\n尚未回复供应商：{no_reply_names}\n"
                    f"已回复 {len(replied)}/{total_cnt} 家，请跟进供应商报价。",
                    is_alert=True)
                notify_markers["warned_30min"] = 1
                sent_events.append("warned_30min")

            # (2) 截止时间到
            if remain_sec <= 0:
                if no_reply:
                    # 有供应商未回复 → 标记超时 + 1 次告警
                    if len(replied) > 0:
                        new_status = "部分供应商超时"
                    else:
                        new_status = "全部供应商超时"
                    if not notify_markers.get("notified_timeout"):
                        timeout_names = "、".join([s.get("name", "") for s in no_reply]) or "无"
                        tool_table_update(table_key="procurement_task", record_id=task_id,
                                          data={"task_status": new_status})
                        tool_send_feishu_message(
                            config.PROC_FEISHU_PM_OPEN_ID,
                            f"🚨询比价已到达截止时间｜任务ID:{task_id}\n"
                            f"状态：{new_status}\n超时未回复：{timeout_names}\n"
                            f"已报价 {len(replied)}/{total_cnt} 家，请人工评估是否继续选型或重新询价。",
                            is_alert=True)
                        notify_markers["notified_timeout"] = 1
                        sent_events.append("notified_timeout")
                else:
                    # 截止时间到但全部已报价 → 1 次提醒选型
                    if not notify_markers.get("notified_all_replied"):
                        tool_send_feishu_message(
                            config.PROC_FEISHU_PM_OPEN_ID,
                            f"✅任务ID:{task_id} 全部供应商报价已回复完成（共{total_cnt}家），请前往平台完成选型确认。")
                        notify_markers["notified_all_replied"] = 1
                        sent_events.append("notified_all_replied")

        # 写回本次新发送的事件标记，下次进度调度即使条件仍然满足也不会重复发
        if sent_events:
            extra_update["notify_markers"] = json.dumps(notify_markers, ensure_ascii=False)
            tool_table_update(table_key="procurement_task", record_id=task_id, data=extra_update)

        results.append({"task_id": task_id, "remain_sec": remain_sec,
                        "total": total_cnt, "replied": len(replied),
                        "no_reply": len(no_reply),
                        "sent_events": sent_events})

    return {"flow": "flow-proc-04", "checked": len(results),
            "total_sent_events": sum(len(r["sent_events"]) for r in results),
            "tasks": results}


def _flow_proc_05_confirm_selection(task: TaskInstance, selected: SupplierItem,
                                     deal_price: float,
                                     skip_feishu_notify: bool = False) -> dict:
    """LLM 组装&发送采购确认邮件 + 飞书通知（选型确认）

    Args:
        skip_feishu_notify: True 时跳过「选型确认完成」飞书新卡片发送。
            用于 source=card_callback 场景：card-callback 会通过返回 {type:"raw", data:<置灰卡片>}
            就地替换原卡片，不需要再额外发一张新卡片通知，避免双卡片。
    """
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

    # LLM 组装确认邮件内容
    ctx = _build_confirm_ctx(task, deal_price, selected.name)
    mail_content = invoke_skill_mail_compose("confirm", ctx)
    subject = mail_content["subject"]
    body = mail_content["body_text"]
    mail_r = tool_send_mail(to=[selected.email], subject=subject, body_text=body,
                            reply_to_mail_id=reply_mail_id, cc=_fetch_global_cc_list())
    mail_r["composed_by"] = mail_content.get("composed_by", "llm")

    feishu_r = {"success": False, "skipped": skip_feishu_notify,
                "error": "open_id 未配置"}
    if (not skip_feishu_notify) and config.PROC_FEISHU_PM_OPEN_ID:
        card = _build_proc_card(task.dict(), "confirm_purchase", {
            "supplier_name": selected.name, "deal_price": deal_price,
        })
        feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

    return {"flow": "flow-proc-05", "mail": mail_r, "feishu": feishu_r,
            "reply_to": reply_mail_id or "无",
            "skip_feishu_notify": skip_feishu_notify,
            "composed_by": mail_content.get("composed_by", "llm")}


def _flow_proc_06_parse_delivery_mail(since_ts: int = 0) -> dict:
    """发货信息解析更新：拉取选中供应商邮件，解析发货时间/物流单号"""
    if not since_ts:
        since_ts = int(time.time()) - 3600  # 默认最近 1 小时
    tasks_r = tool_table_query(table_key="procurement_task",
                               filter={"task_status": "已选型确认"}, page_size=50)
    if not tasks_r.get("success"):
        return {"flow": "flow-proc-06", "error": tasks_r.get("error")}

    supplier_emails = []
    task_map = {}  # email → task
    for t in tasks_r.get("records", []):
        sel = json.loads(t.get("selected_supplier", "null") or "null")
        if sel and sel.get("email"):
            supplier_emails.append(sel["email"])
            task_map[sel["email"]] = t

    if not supplier_emails:
        return {"flow": "flow-proc-06", "note": "无待发货任务"}

    mails_r = tool_read_inbox_mail(since_timestamp=since_ts,
                                   filter_sender_email_list=supplier_emails)
    if not mails_r.get("success"):
        return {"flow": "flow-proc-06", "error": mails_r.get("error")}

    results = []
    for m in mails_r.get("mails", []):
        from_email = m.get("from_email", "")
        body = m.get("mail_body_text", "")
        task = task_map.get(from_email)
        if not task:
            continue
        # 🤖 调用 LLM Skill (skill-proc-parse) 解析物流信息，正则作为可选 Tool 由 LLM 决定是否调用
        # LLM 失败时 invoke_skill_parse 内部会 fallback 到 robust_parse_logistics_info 兜底
        # 字段映射：LLM 输出 tracking_no，这里取 logistics_no（双键都有，取兼容字段名）
        logi = invoke_skill_parse(
            "skill-proc-parse",
            mail_body=body,
            parse_mode="logistics",
            expected_qty=0,
            spare_part_model="",
        )
        logistics_no = logi.get("logistics_no", "") or logi.get("tracking_no", "")
        carrier = logi.get("carrier", "")
        delivery_date = logi.get("delivery_date", "")
        # 发货时间：优先邮件里抽出来的日期，再退回收件时间
        delivery_time = delivery_date or datetime.fromtimestamp(
            m.get("receive_timestamp") or time.time()).strftime("%Y-%m-%d %H:%M:%S")

        if logistics_no:
            tool_table_update(table_key="procurement_task", record_id=task["task_id"],
                              data={
                                  "delivery_time": delivery_time,
                                  "logistics_no": logistics_no,
                                  "logistics_carrier": carrier or "",  # 扩展字段：载体
                                  "logistics_raw": logi["raw_excerpt"],  # 原始邮件片段，方便人工复核
                                  "task_status": "供应商发货中"
                              })
            if config.PROC_FEISHU_PM_OPEN_ID:
                td = dict(task)
                td["delivery_time"] = delivery_time
                td["logistics_no"] = logistics_no
                card = _build_proc_card(td, "delivery")
                tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
            results.append({"task_id": task["task_id"], "logistics_no": logistics_no,
                            "delivery_time": delivery_time})

    return {"flow": "flow-proc-06", "total": len(results), "updates": results}


def _flow_proc_07_input_test_result(task: TaskInstance, test_result: str,
                                     remark: str = "") -> dict:
    """测试结果录入处理：
    通过 → 写台账 + 闭环 + 飞书通知 + LLM 组装&发验收邮件给供应商（reply_to 报价邮件线程）
    失败 → 飞书告警
    """
    if test_result == "通过":
        # 触发 flow-proc-08 写台账
        ledger_r = _flow_proc_08_write_ledger(task)
        # 闭环
        tool_table_update(table_key="procurement_task", record_id=task.task_id,
                          data={"task_status": "流程闭环", "ledger_written": 1})
        # 飞书通知闭环
        feishu_r = {"success": False}
        if config.PROC_FEISHU_PM_OPEN_ID:
            card = _build_proc_card(task.dict(), "ledger_written")
            feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)

        # LLM 组装验收邮件给供应商（reply_to 报价邮件线程）
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
            ctx = {
                "project_name": task.project_name,
                "contract_no": task.contract_no,
                "spare_part_model": task.spare_part_model,
                "purchase_qty": task.purchase_qty,
                "deal_unit_price": task.deal_unit_price or 0,
                "supplier_name": sel_name,
                "task_id": task.task_id,
            }
            mail_content = invoke_skill_mail_compose("acceptance", ctx)
            mail_r = tool_send_mail(to=[sel_email],
                                    subject=mail_content["subject"],
                                    body_text=mail_content["body_text"],
                                    reply_to_mail_id=reply_mail_id or None,
                                    cc=_fetch_global_cc_list())
            mail_r["composed_by"] = mail_content.get("composed_by", "llm")

        return {"flow": "flow-proc-07", "result": "pass", "ledger": ledger_r,
                "feishu": feishu_r, "acceptance_mail": mail_r}
    else:
        feishu_r = {"success": False}
        if config.PROC_FEISHU_PM_OPEN_ID:
            card = _build_proc_card(task.dict(), "test_failed")
            feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
        return {"flow": "flow-proc-07", "result": "fail", "remark": remark, "feishu": feishu_r}


def _flow_proc_08_write_ledger(task: TaskInstance) -> dict:
    """台账写入：从 task 提取字段写入 procurement_ledger 表（SQLite 主 + 飞书多维表格副本双写）

    幂等策略（重点修复：之前用 task_status=="流程闭环" 判断是错的 —— 因为 9006 端会在调 neuops 前
    先把任务状态改成闭环，导致 neuops 端永远跳过、双写飞书副本漏执行）：

      1. 先查 SQLite procurement_ledger 表是否存在该 task_id：
         - 若已存在 → 不重复写 SQLite，继续尝试"飞书多维表格副本同步"（将来接入时在这里执行）
         - 若不存在 → 正常写 SQLite，再尝试飞书副本同步
      2. 飞书多维表格副本同步 TODO：当前代码尚未接入飞书 bitable，返回 ledger_feishu_bitable=todo
         等拿到飞书多维表格的 app_token + table_id，再在 TODO 处补 sync_to_bitable(data)。
    """
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

    # 1) 查 SQLite 主库是否已写入（9006 端 write_ledger 会先于 neuops 触发，所以这里要兼容）
    check = tool_table_query(table_key="procurement_ledger",
                             filter={"task_id": task.task_id}, page_size=1)
    sqlite_existed = bool(check.get("success") and check.get("records"))

    sqlite_r = {"success": True, "note": "9006端已先写入，存在即正确，跳过本地INSERT"}
    if not sqlite_existed:
        sqlite_r = tool_table_insert(table_key="procurement_ledger", data=ledger_data)

    # 2) 飞书多维表格副本同步（TODO 待配置：需要飞书多维表格 app_token + table_id）
    #    接入方式：构造相同 ledger_data 作为 bitable 记录，
    #    POST https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records
    #    幂等：飞书侧用 task_id 做唯一键（字段值匹配即视为已存在）
    feishu_ledger = {"status": "todo", "note": "飞书多维表格app_token/table_id未配置，双写副本待接入"}

    return {"flow": "flow-proc-08",
            "ledger_sqlite": {"existed_before": sqlite_existed, "insert_result": sqlite_r.get("success"),
                              "ledger_id": sqlite_r.get("record_id") if sqlite_r.get("success") and not sqlite_existed else "(9006端预写)"},
            "ledger_feishu_bitable": feishu_ledger}


def _flow_proc_09_cancel_task(task: TaskInstance, cancel_reason: str) -> dict:
    """任务取消处理：contract 工程已 table_update 状态=任务已取消 + cancel_reason，
    neuops 端飞书通知（交互卡片）"""
    feishu_r = {"success": False}
    if config.PROC_FEISHU_PM_OPEN_ID:
        td = task.dict()
        td["cancel_reason"] = cancel_reason
        card = _build_proc_card(td, "task_canceled")
        feishu_r = tool_send_feishu_card(config.PROC_FEISHU_PM_OPEN_ID, card)
    return {"flow": "flow-proc-09", "task_id": task.task_id, "feishu": feishu_r}


# ════════════════════════════════════════════════════════════════
# Trigger endpoint（contract 工程调用）
# ════════════════════════════════════════════════════════════════
@router.post("/trigger/task-created")
async def trigger_task_created(task: TaskInstance):
    """contract 工程 create_task 成功后调用：触发 flow-proc-01 + flow-proc-02"""
    r1 = _flow_proc_01_create_task(task)
    r2 = _flow_proc_02_send_inquiry_mail(task)
    return {"success": True, "trigger": "task-created", "task_id": task.task_id,
            "flow_01": r1, "flow_02": r2}


@router.post("/trigger/task-selected")
async def trigger_task_selected(body: SelectionBody):
    """contract 工程选型确认后调用：触发 flow-proc-05

    body.source == "card_callback" 时会跳过 confirm_purchase 飞书通知卡片发送，
    避免和 card-callback 返回的就地替换置灰卡片造成双卡片。
    """
    skip_feishu = (body.source or "").lower() == "card_callback"
    r = _flow_proc_05_confirm_selection(body.task, body.selected_supplier,
                                         body.deal_unit_price,
                                         skip_feishu_notify=skip_feishu)
    return {"success": True, "trigger": "task-selected", "task_id": body.task.task_id,
            "source": body.source, "skip_feishu_notify": skip_feishu, "flow_05": r}


@router.post("/trigger/test-result")
async def trigger_test_result(body: TestResultBody):
    """contract 工程录入测试结果后调用：触发 flow-proc-07（内部联动 flow-proc-08）"""
    r = _flow_proc_07_input_test_result(body.task, body.test_result, body.remark)
    return {"success": True, "trigger": "test-result", "task_id": body.task.task_id, "flow_07": r}


@router.post("/trigger/task-canceled")
async def trigger_task_canceled(body: CancelBody):
    """contract 工程取消任务后调用：触发 flow-proc-09"""
    r = _flow_proc_09_cancel_task(body.task, body.cancel_reason)
    return {"success": True, "trigger": "task-canceled", "task_id": body.task.task_id, "flow_09": r}


# ════════════════════════════════════════════════════════════════
# Scheduler tick（定时调度器入口，由外部 systemd timer / asyncio loop 调用）
# ════════════════════════════════════════════════════════════════
@router.post("/scheduler/tick")
async def scheduler_tick(kind: str = "all"):
    """定时调度入口
    kind=quote → flow-proc-03 报价解析（每 5 分钟）
    kind=progress → flow-proc-04 进度告警（每 60 分钟）
    kind=delivery → flow-proc-06 发货解析（每 5 分钟）
    kind=all → 全部依次执行
    """
    results = {}
    if kind in ("quote", "all"):
        results["flow_03"] = _flow_proc_03_parse_quote_mails()
    if kind in ("progress", "all"):
        results["flow_04"] = _flow_proc_04_progress_and_alert()
    if kind in ("delivery", "all"):
        results["flow_06"] = _flow_proc_06_parse_delivery_mail()
    if kind in ("mail-inquiry", "all"):
        # 备件邮件询价流程引擎（独立状态机，每 tick 推进 N 个任务）
        results["mail_inquiry"] = tick_mail_inquiry()
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

    飞书回调响应返回格式（2025 起 Interactive Card 协议严格要求）：
      - 只能包含飞书认识的字段：toast / card / ... 不允许 success 等自定义字段，
        否则客户端直接报 code=200341「出错了，请稍后重试」。
      - toast 用于弹出轻提示；card 会就地替换原卡片（用于置灰按钮）。
    """
    import logging as _lg
    _log = _lg.getLogger("card_callback")

    def _warn(msg, *a):
        try:
            txt = msg if not a else msg % a
            _log.warning("[card_callback] %s", txt)
            print(f"[card_callback] {txt}", flush=True)
        except Exception:
            pass

    raw = await request.body()
    _warn("raw bytes=%d preview=%s", len(raw), raw[:400])
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as e:
        _warn("JSON parse fail: %s", e)
        # 返回格式务必干净，避免触发 200341
        return {"toast": {"type": "error", "content": "请求解析失败，请重试"}}

    _warn("top keys=%s", list(body.keys()))

    # 1. challenge（首次配置回调 URL 校验）
    if "challenge" in body:
        _warn("回复 challenge=%s", str(body["challenge"])[:30])
        return {"challenge": body["challenge"]}

    # 2. 解析 action.value（兼容两种 payload 结构）
    action_data = {}
    if isinstance(body.get("action"), dict):
        action_data = body["action"].get("value", {}) or {}
        _warn("A path body.action.value -> %s", action_data)
    if not action_data and isinstance(body.get("event"), dict):
        evt = body["event"]
        if isinstance(evt.get("action"), dict):
            action_data = evt["action"].get("value", {}) or {}
            _warn("B path body.event.action.value -> %s", action_data)
        else:
            _warn("body.event keys=%s", list(evt.keys()))

    action = action_data.get("action", "")
    open_id = (body.get("open_id")
               or (isinstance(body.get("event"), dict)
                   and isinstance(body["event"].get("operator"), dict)
                   and body["event"]["operator"].get("open_id", ""))
               or "")
    _warn("final action=%s open_id=%s data=%s", action, open_id, action_data)

    # 3. 执行业务逻辑
    if action == "confirm_purchase":
        try:
            result = await _handle_confirm_purchase_action(action_data)
        except Exception as e:
            _warn("confirm_purchase EXCEPTION %s: %s", type(e).__name__, e)
            return {"toast": {"type": "error",
                              "content": f"选型处理失败: {type(e).__name__}: {e}"[:60]}}
        mail_ok = result.get("mail", {}).get("success", False)
        new_card = result.get("card")
        _warn("confirm_purchase done mail_ok=%s has_new_card=%s", mail_ok, bool(new_card))
        # 👇 严格按飞书新版 schema 2.0 card.action.trigger 协议返回：
        #   - 顶层只能有 toast / card
        #   - card 字段必须是 {"type": "raw", "data": <卡片实际 JSON>} 结构
        #   不允许出现 success / action / mail 等自定义字段，否则触发 200341
        supplier_name = action_data.get("supplier_name") or "供应商"
        resp = {"toast": {"type": "success",
                          "content": f"选型已确认，将向 {supplier_name} 发送采购邮件"}}
        if isinstance(new_card, dict) and new_card:
            resp["card"] = {"type": "raw", "data": new_card}
        return resp

    # 未知 action，返回 toast 占位，避免 200341
    _warn("未知 action=%s，占位返回", action)
    return {"toast": {"type": "info",
                      "content": f"已收到按钮点击(action={action})，无需后续操作"[:60]}}


async def _handle_confirm_purchase_action(action_data: dict) -> dict:
    """处理飞书卡片「确认采购」按钮回调
    1. 调 contract 9006 API 更新 task 状态（confirm_selection）——透传 source=card_callback，
       让 9006 的 trigger_neuops 调用 flow-proc-05 时不再额外发 confirm_purchase 飞书卡片
       （因为本函数返回的 raw card 会就地替换原卡片为置灰效果，避免双卡片）
    2. 发采购确认邮件给供应商（reply_to 报价邮件线程）
    3. 返回置灰卡片（会以 {"type":"raw","data":card} 形式响应飞书请求，就地替换原卡片）
    """
    task_id = action_data.get("task_id", "")
    supplier_name = action_data.get("supplier_name", "")
    supplier_email = action_data.get("supplier_email", "")
    deal_price = action_data.get("deal_price", 0)
    reply_mail_id = action_data.get("reply_mail_id", "")

    if not task_id or not supplier_email:
        return {"success": False, "error": "task_id 或 supplier_email 缺失"}

    # 1. 调 contract 9006 API 确认选型（更新 task 状态 + 操作日志）
    #    传 source=card_callback，9006 端会透传给 trigger/task-selected → flow-proc-05 跳过多余的飞书通知
    task = {}
    try:
        import httpx
        r = httpx.post(f"http://127.0.0.1:9006/api/procurement/tasks/{task_id}/select",
                       json={"selected_supplier": {"name": supplier_name, "email": supplier_email},
                             "deal_unit_price": float(deal_price),
                             "source": "card_callback"}, timeout=10)
        contract_r = r.json()
        task = contract_r.get("data", {}) or {}
    except Exception:
        task = {}
    # 9006 没有此任务（测试 task_id）时 fallback 到 SQLite 兜底更新，确保 DB 有记录
    if not task:
        task_r = tool_table_query(table_key="procurement_task",
                                  filter={"task_id": task_id}, page_size=1)
        records = task_r.get("records", []) if isinstance(task_r, dict) else []
        task = (records[0] if records else {}) or {}
        # 不存在就插入，存在就更新，确保 trigger/task-selected 下次拿到完整 task 不会 422
        if not task:
            tool_table_insert(table_key="procurement_task", data={
                "task_id": task_id,
                "project_id": "", "project_name": "卡片回调测试任务",
                "contract_no": "", "spare_part_model": "测试备件",
                "purchase_qty": 0, "emergency_level": "4h",
                "reply_deadline": "",
                "inquiry_supplier_list": json.dumps([
                    {"name": supplier_name, "email": supplier_email}]),
                "replied_supplier_quotes": json.dumps([{
                    "supplier_name": supplier_name, "email": supplier_email,
                    "unit_price": deal_price, "reply_time": datetime.now().strftime("%F %T")}]),
                "no_reply_supplier": "[]",
                "selected_supplier": json.dumps({"name": supplier_name, "email": supplier_email}),
                "deal_unit_price": deal_price, "task_status": "已选型确认",
                "cancel_reason": "", "creator": "pm",
                "create_time": datetime.now().strftime("%F %T"),
            })
        else:
            tool_table_update(table_key="procurement_task", record_id=task_id, data={
                "task_status": "已选型确认",
                "selected_supplier": json.dumps({"name": supplier_name, "email": supplier_email}),
                "deal_unit_price": deal_price,
            })
        task_r2 = tool_table_query(table_key="procurement_task", filter={"task_id": task_id}, page_size=1)
        if isinstance(task_r2, dict) and task_r2.get("records"):
            task = task_r2["records"][0]

    # 2. 发采购确认邮件给供应商（reply_to 报价邮件线程）
    contract = _lookup_contract(str(task.get('contract_no', '')))
    subject = f"【采购确认】任务ID:{task_id}｜{task.get('project_name', '')} {task.get('spare_part_model', '')} 备品备件确认采购"
    body_text = CONFIRM_MAIL_TPL.format(
        purchase_qty=task.get("purchase_qty", ""),
        delivery_deadline="",
        spare_part_model=task.get("spare_part_model", ""),
        receiver_address=contract.get("receiver_address", ""),
        receiver_name=contract.get("receiver_name", ""),
        receiver_phone=contract.get("receiver_phone", ""),
    )
    mail_r = tool_send_mail(to=[supplier_email], subject=subject, body_text=body_text,
                            reply_to_mail_id=reply_mail_id or None, cc=_fetch_global_cc_list())

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





# ════════════════════════════════════════════════════════════════
# 备件邮件询价流程引擎（阶段 2）
# ── 严格最小侵入：全部新代码追加在文件末尾，不改动 2265 行之前任何现有函数。
# ── 架构：静态配置走 skill JSON；动态状态走 spare_mail_task 单表；
#           流程驱动走 scheduler/tick?kind=mail-inquiry 定时轮询。
# ════════════════════════════════════════════════════════════════

# ── 模块级延迟 import（避免改文件顶部 import 区）──
def _ensure_mail_inquiry_imports():
    """首次调用时把 CRUD / schema / skill_loader / employees 加载进来。"""
    import importlib, sys
    try:
        from app.db import spare_mail as _spm; _ensure_mail_inquiry_imports._spm = _spm
        from app.db.schema import init_spare_mail_db as _init_db; _ensure_mail_inquiry_imports._init_db = _init_db
        from app.db.employees import db_upsert_employee as _upsert_emp; _ensure_mail_inquiry_imports._upsert_emp = _upsert_emp
        from app.skill_loader import load_skill as _load_sk; _ensure_mail_inquiry_imports._load_sk = _load_sk
    except Exception as e:
        raise RuntimeError(f"mail-inquiry imports failed: {e}")

# ── 常量 ──
_SKILL_ID_MAIL_INQUIRY = "skill-proc-mail-inquiry"
_TICK_MAX_TASKS = 5          # 每 tick 最多推进 N 个任务
_DEFAULT_SINCE_MINUTES = 120  # 读邮件窗口（2h）
_INTERNAL_KEYWORDS = ("备件", "询价", "采购", "备件询价", "备件采购")

# ── 工具函数 ──
def _norm_mid(m):
    """规范化 RFC Message-ID（去掉前后 <>）。"""
    s = str(m or "").strip()
    while s.startswith("<"): s = s[1:]
    while s.endswith(">"):   s = s[:-1]
    return s.strip()

def _load_mail_inquiry_skill():
    """从 skill_loader 热加载 skill-proc-mail-inquiry，返回 (config_dict, templates_dict)。
    失败时返回 (None, None)。"""
    try:
        _ensure_mail_inquiry_imports()
        sk = _ensure_mail_inquiry_imports._load_sk(_SKILL_ID_MAIL_INQUIRY)
        if not sk:
            return None, None
        skill_def = sk.get("skill") or {}
        return skill_def.get("config") or {}, skill_def.get("templates") or {}
    except Exception as e:
        print(f"[mail-inquiry] load skill failed: {e}")
        return None, None

def _gen_task_id() -> str:
    """生成 MI-{timestamp}-{rand6} 格式的任务号。"""
    import random
    ts = int(time.time())
    r = ''.join(random.choices('abcdef0123456789', k=6))
    return f"MI-{ts}-{r}"

def _inquiry_deadline_ts(inquiry_dur: str) -> int:
    """询价时限换算成 Unix 时间戳（截止时刻）。"""
    dur = str(inquiry_dur or "48h").lower()
    mapping = {"12h": 12 * 3600, "24h": 24 * 3600, "48h": 48 * 3600}
    secs = mapping.get(dur, 48 * 3600)
    return int(time.time()) + secs

def _safe_json_loads(s, default=None):
    if default is None: default = []
    if not s: return default
    try: return json.loads(s)
    except Exception: return default


def _safe_format(template: str, args: dict) -> str:
    """安全 format：模板占位符缺失时用空字符串兜底，防止崩。"""
    if not template:
        return ""
    try:
        return template.format(**args)
    except KeyError:
        # 有占位符没提供 → 尝试只补缺失的为空串
        import re as _re
        missing = set()
        for m in _re.finditer(r"\{(\w+)\}", template):
            key = m.group(1)
            if key not in args:
                missing.add(key)
        fixed = dict(args)
        for k in missing:
            fixed[k] = ""
        try:
            return template.format(**fixed)
        except Exception:
            return template
    except Exception:
        return template


# ── 主循环：tick_mail_inquiry ──
def tick_mail_inquiry():
    """每次被 scheduler/tick?kind=mail-inquiry 调用时执行。

    1) 确保 DB 表存在（幂等）。
    2) 从 PARSING/SENDING_B/WAITING_QUOTES/DECIDING_LOWEST/WAITING_APPROVAL/ORDERING
       六个状态各取最多 N/TICK 个任务推进。
    3) 每个 step 推进独立 try/except，单任务崩不阻塞其他。
    """
    _ensure_mail_inquiry_imports()
    try:
        _ensure_mail_inquiry_imports._init_db()
    except Exception as e:
        print(f"[mail-inquiry] init_spare_mail_db failed: {e}")

    cfg, tpls = _load_mail_inquiry_skill()
    if not cfg:
        return {"enabled": False, "msg": "skill-proc-mail-inquiry 未加载", "progress": 0}
    if not cfg.get("mail_enabled", True):
        return {"enabled": False, "msg": "mail_enabled=false 已停用", "progress": 0}

    progress = 0
    step_stats = {}

    # ── Step 1: PARSING — 读收件箱拉"工程师发起询价"的内部邮件并落任务 ──
    try:
        step_stats["PARSING"] = _step_parsing(cfg, tpls)
        progress += step_stats["PARSING"].get("created", 0)
    except Exception as e:
        step_stats["PARSING"] = {"error": str(e)}

    # ── Step 2: SENDING_B — 对新任务发对外询价邮件 ──
    try:
        tasks_b = _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(
            filter={"status": "SENDING_B"}, page_size=_TICK_MAX_TASKS)
        for t in tasks_b:
            try:
                _step_sending_b(t, cfg, tpls)
                progress += 1
            except Exception as e:
                _ensure_mail_inquiry_imports._spm.spare_mail_update_task(
                    t["task_id"], {"latest_step": f"SENDING_B_ERROR:{e}", "updated_at": ""})
        step_stats["SENDING_B"] = {"processed": len(tasks_b)}
    except Exception as e:
        step_stats["SENDING_B"] = {"error": str(e)}

    # ── Step 3: WAITING_QUOTES — 拉供应商报价回复（线程匹配 B 的 Message-ID） ──
    try:
        tasks_waiting = _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(
            filter={"status": "WAITING_QUOTES"}, page_size=_TICK_MAX_TASKS * 3)
        for t in tasks_waiting:
            try:
                if _step_waiting_quotes(t, cfg, tpls):
                    progress += 1
            except Exception as e:
                _ensure_mail_inquiry_imports._spm.spare_mail_update_task(
                    t["task_id"], {"latest_step": f"WAITING_QUOTES_ERROR:{e}"})
        step_stats["WAITING_QUOTES"] = {"scanned": len(tasks_waiting)}
    except Exception as e:
        step_stats["WAITING_QUOTES"] = {"error": str(e)}

    # ── Step 4: DECIDING_LOWEST — 到点/全部供应商已回 → 汇总最低价 + 内部审批 ──
    try:
        tasks_deciding = _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(
            filter={"status": "DECIDING_LOWEST"}, page_size=_TICK_MAX_TASKS)
        for t in tasks_deciding:
            try:
                _step_deciding_lowest(t, cfg, tpls)
                progress += 1
            except Exception as e:
                _ensure_mail_inquiry_imports._spm.spare_mail_update_task(
                    t["task_id"], {"latest_step": f"DECIDING_ERROR:{e}"})
        step_stats["DECIDING_LOWEST"] = {"processed": len(tasks_deciding)}
    except Exception as e:
        step_stats["DECIDING_LOWEST"] = {"error": str(e)}

    # ── Step 5: WAITING_APPROVAL — 读审批人回复，路由批准/拒绝/指定供应商 ──
    try:
        tasks_app = _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(
            filter={"status": "WAITING_APPROVAL"}, page_size=_TICK_MAX_TASKS)
        for t in tasks_app:
            try:
                _step_waiting_approval(t, cfg, tpls)
                progress += 1
            except Exception as e:
                _ensure_mail_inquiry_imports._spm.spare_mail_update_task(
                    t["task_id"], {"latest_step": f"APPROVAL_ERROR:{e}"})
        step_stats["WAITING_APPROVAL"] = {"processed": len(tasks_app)}
    except Exception as e:
        step_stats["WAITING_APPROVAL"] = {"error": str(e)}

    # ── Step 6: ORDERING — 下达订货邮件给选中供应商 ──
    try:
        tasks_order = _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(
            filter={"status": "ORDERING"}, page_size=_TICK_MAX_TASKS)
        for t in tasks_order:
            try:
                _step_ordering(t, cfg, tpls)
                progress += 1
            except Exception as e:
                _ensure_mail_inquiry_imports._spm.spare_mail_update_task(
                    t["task_id"], {"latest_step": f"ORDERING_ERROR:{e}"})
        step_stats["ORDERING"] = {"processed": len(tasks_order)}
    except Exception as e:
        step_stats["ORDERING"] = {"error": str(e)}

    return {"enabled": True, "progress": progress, "step_stats": step_stats}


# ════════════════════════════════════════════════════════════════
# Step 实现
# ════════════════════════════════════════════════════════════════

def _step_parsing(cfg, tpls):
    """PARSING 状态：读收件箱找工程师发起询价的内部邮件 → 建任务 → 转到 SENDING_B。"""
    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60
    # 黑名单：采购方自己的邮箱（排除 sent 副本）
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = tool_read_inbox_mail(since_timestamp=since_ts, exclude_sender_email_list=exclude)
    created = 0
    if not r.get("success"):
        return {"created": 0, "msg": r.get("error", "read inbox failed")}

    # 已创建的 thread_msg_id 集合（避免重复入库）
    existing_threads = {
        t.get("thread_msg_id", "") for t in
        _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(page_size=500)
    }

    for m in r.get("mails", []):
        body = (m.get("mail_body_text") or "")
        subject = (m.get("subject") or "")
        mid = _norm_mid(m.get("message_id", ""))
        if not mid or mid in existing_threads:
            continue

        # 命中关键词 → 判定为"工程师发起询价"邮件
        body_flat = re.sub(r"\s+", "", body + subject)
        if not any(kw in body_flat for kw in _INTERNAL_KEYWORDS):
            continue

        # 从正文抽取字段（尽量解析，不完整就留空由后续补）
        fields = _extract_inquiry_fields(body, subject)
        task_id = _gen_task_id()
        deadline = _inquiry_deadline_ts(fields.get("inquiry_dur", "48h"))

        task = {
            "task_id": task_id,
            "thread_msg_id": mid,
            "project_no": fields.get("project_no", ""),
            "project_name": fields.get("project_name", ""),
            "part_type": fields.get("part_type", ""),
            "brand": fields.get("brand", ""),
            "pn": fields.get("pn", ""),
            "spec": fields.get("spec", ""),
            "condition": fields.get("condition", ""),
            "count": fields.get("count", ""),
            "address": fields.get("address", ""),
            "inquiry_dur": fields.get("inquiry_dur", "48h"),
            "latest_ship_time": fields.get("latest_ship_time", ""),
            "inquiry_deadline": datetime.fromtimestamp(deadline).strftime("%Y-%m-%d %H:%M:%S"),
            "suppliers_json": "[]",
            "quotes_json": "[]",
            "status": "SENDING_B",
            "latest_step": "PARSING→SENDING_B",
        }
        _ensure_mail_inquiry_imports._spm.spare_mail_create_task(task)
        existing_threads.add(mid)
        created += 1

    return {"created": created, "total_scanned": len(r.get("mails", []))}


def _extract_inquiry_fields(body: str, subject: str) -> dict:
    """从工程师询价邮件正文抽取关键字段（正则规则，失败返回空字符串占位）。"""
    merged = (body or "") + "\n" + (subject or "")
    out = {}
    # 项目编号
    m = re.search(r"(?:项目(?:编号|号)?\s*[:：]?\s*)(PRJ[-_/\w\d]+)", merged, re.I)
    if m: out["project_no"] = m.group(1)
    # 项目名称
    m = re.search(r"(?:项目名称?\s*[:：]?\s*)([\u4e00-\w\-（）()\s]{2,40})", merged)
    if m and "project_name" not in out: out["project_name"] = m.group(1).strip()
    # 品牌
    m = re.search(r"(?:品牌\s*[:：]?\s*)([A-Za-z][A-Za-z0-9\-]{2,20})", merged)
    if m: out["brand"] = m.group(1)
    # PN
    m = re.search(r"(?:PN(?:\s*料号)?\s*[:：]?\s*)([A-Za-z0-9\-/.]{4,30})", merged, re.I)
    if m: out["pn"] = m.group(1)
    # 备件类型
    m = re.search(r"(?:备件(?:类型)?\s*[:：]?\s*)(内存条|硬盘|电源|主板|网卡|CPU|机箱|风扇|SSD|HDD)", merged)
    if m: out["part_type"] = m.group(1)
    # 成色
    m = re.search(r"(成色\s*[:：]?\s*)(全新|原厂翻新|拆机二手)", merged)
    if m: out["condition"] = m.group(1)
    # 数量
    m = re.search(r"(?:采购数量|数量)\s*[:：]?\s*(\d+)", merged)
    if m: out["count"] = m.group(1)
    # 询价时限
    m = re.search(r"(?:(?:询价)?回复(?:时限|时间|内))\s*[:：]?\s*(\d+\s*[hH小时])", merged)
    if m:
        dur = m.group(1).lower().replace("小时", "h").replace(" ", "")
        dur_map = {"12h": "12h", "24h": "24h", "48h": "48h", "12h": "12h"}
        out["inquiry_dur"] = dur_map.get(dur, dur) if dur_map.get(dur) else dur
    # 最晚发货时间
    m = re.search(r"(?:最晚发货(?:时间)?\s*[:：]?\s*)(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)", merged)
    if m: out["latest_ship_time"] = m.group(1).replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
    # 规格
    m = re.search(r"(?:规格(?:参数)?\s*[:：]?\s*)([\u4e00-\w\d\s+/\-]{4,60})", merged)
    if m: out["spec"] = m.group(1).strip()
    return out


def _step_sending_b(task: dict, cfg: dict, tpls: dict):
    """SENDING_B：渲染模板 B（不带收货地址）→ tool_batch_send_mail → 存 suppliers_json → WAITING_QUOTES。"""
    tid = task["task_id"]
    tpl_b = (tpls or {}).get("B", {}) or {}

    # 供应商池：优先查 tool_table_query（主数据表），失败/无记录 fallback 空数组
    suppliers = []
    try:
        r = tool_table_query(table_key="procurement_master_data", page_size=20)
        records = r.get("records", []) if isinstance(r, dict) else []
        for rec in records:
            name = str(rec.get("supplier_name") or rec.get("name") or "").strip()
            email = str(rec.get("supplier_email") or rec.get("email") or "").strip()
            if name and email:
                suppliers.append({"name": name, "email": email})
    except Exception:
        pass
    if not suppliers:
        # 兼容 skill config 里可能的 default_suppliers 占位
        for s in (cfg or {}).get("default_suppliers", []) or []:
            name = str(s.get("name") or "").strip() if isinstance(s, dict) else str(s)
            email = str(s.get("email") or "").strip() if isinstance(s, dict) else ""
            if name and email:
                suppliers.append({"name": name, "email": email})

    # 渲染模板 B（每个供应商各渲染一份，supplier 字段不同）
    deadline_str = task.get("inquiry_deadline") or ""
    emails = [s["email"] for s in suppliers]
    subject = (tpl_b.get("subject") or "").format(
        project_no=task.get("project_no", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        count=task.get("count", ""),
        inquiry_dur=task.get("inquiry_dur", "48h"),
    )
    body_fmt = tpl_b.get("body") or ""
    body_args = dict(
        project_no=task.get("project_no", ""),
        project_name=task.get("project_name", ""),
        part_type=task.get("part_type", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        spec=task.get("spec", ""),
        condition=task.get("condition", ""),
        count=task.get("count", ""),
        latest_ship_time=task.get("latest_ship_time", ""),
        inquiry_dur=task.get("inquiry_dur", "48h"),
        deadline=deadline_str,
        task_no=tid,
        supplier="{supplier}",
    )
    # 批量发送（同一个 body 模板，每封的 {supplier} 事后回填——这里统一批发送完再组装）
    rendered_body = body_fmt.format(**body_args).replace("{supplier}", "供应商您好")
    batch_r = tool_batch_send_mail(receiver_email_list=emails, subject=subject, body_text=rendered_body)

    # 组装 suppliers_json
    sent_map = {(s.get("email") or ""): (s.get("message_id") or "") for s in batch_r.get("sent", [])}
    fail_set = {(f.get("email") or "") for f in batch_r.get("fail_email_list", [])}
    suppliers_out = []
    for s in suppliers:
        email = s["email"]
        msg_id = sent_map.get(email, "")
        ok = email not in fail_set and bool(msg_id)
        suppliers_out.append({
            "name": s["name"], "email": email, "msg_id": msg_id, "sent_ok": ok,
        })

    # 存库并转到 WAITING_QUOTES
    spm = _ensure_mail_inquiry_imports._spm
    spm.spare_mail_update_task(tid, {
        "suppliers_json": json.dumps(suppliers_out, ensure_ascii=False),
        "status": "WAITING_QUOTES",
        "latest_step": f"SENDING_B→WAITING_QUOTES(sent={sum(1 for x in suppliers_out if x['sent_ok'])}/{len(suppliers_out)})",
    })
    return True


def _step_waiting_quotes(task: dict, cfg: dict, tpls: dict) -> bool:
    """WAITING_QUOTES：拉邮件 → 按 In-Reply-To/References 匹配 B 的 Message-ID → 解析报价 → 到点或全供应商已回 → DECIDING_LOWEST。

    返回 True 表示任务已推进到下一状态。
    """
    tid = task["task_id"]
    suppliers = _safe_json_loads(task.get("suppliers_json") or "[]")
    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    existing_msg_ids = {_norm_mid(q.get("msg_id", "")) for q in quotes}

    # 要匹配的 Message-ID：每个成功发送的 B 邮件
    match_ids = [_norm_mid(s.get("msg_id", "")) for s in suppliers if s.get("sent_ok") and s.get("msg_id")]
    if not match_ids:
        # 没有发成功的询价邮件，直接转 DECIDING_LOWEST（此时 quotes=[] → 走无有效报价分支）
        _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
            "status": "DECIDING_LOWEST",
            "latest_step": "WAITING_QUOTES→DECIDING_LOWEST(no_sent_suppliers)",
        })
        return True

    # 拉收件箱：用 match_in_reply_to_msg_ids 精确匹配线程
    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60 * 2
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = tool_read_inbox_mail(since_timestamp=since_ts, exclude_sender_email_list=exclude,
                             match_in_reply_to_msg_ids=match_ids)

    new_quotes_added = False
    if r.get("success"):
        for m in r.get("mails", []):
            mid = _norm_mid(m.get("message_id", ""))
            if not mid or mid in existing_msg_ids:
                continue
            # 发件人必须在我们的供应商列表里
            from_email = str(m.get("from_email") or "").lower()
            matched_supplier = None
            for s in suppliers:
                if str(s.get("email") or "").lower() == from_email:
                    matched_supplier = s
                    break
            if not matched_supplier:
                continue

            # 解析报价正文：单价/成色/数量/发货时间
            body = m.get("mail_body_text") or ""
            parsed = _parse_quote_body(body)

            # 迟到判断
            deadline_str = task.get("inquiry_deadline", "")
            try:
                from email.utils import parsedate_to_datetime
                recv_ts = int(m.get("receive_timestamp") or 0)
                deadline_ts = int(datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S").timestamp()) if deadline_str else 0
                is_late = bool(recv_ts and deadline_ts and recv_ts > deadline_ts)
            except Exception:
                is_late = False

            quotes.append({
                "supplier": matched_supplier.get("name", ""),
                "email": from_email,
                "unit_price": parsed.get("unit_price", ""),
                "condition": parsed.get("condition", ""),
                "count": parsed.get("count", ""),
                "ship_time": parsed.get("ship_time", ""),
                "msg_id": mid,
                "is_late": is_late,
                "raw_subject": m.get("subject", ""),
                "raw_body": body[:800],
            })
            existing_msg_ids.add(mid)
            new_quotes_added = True

    # 判断是否到点/全部已回
    all_replied = all(
        not s.get("sent_ok")
        or any(str(q.get("email") or "").lower() == str(s.get("email") or "").lower()
               for q in quotes)
        for s in suppliers
    )
    deadline_str = task.get("inquiry_deadline", "")
    try:
        import time as _time
        deadline_ts = int(datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S").timestamp()) if deadline_str else 0
    except Exception:
        deadline_ts = 0
    now_ts = int(time.time())

    if all_replied or (deadline_ts and now_ts >= deadline_ts):
        _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
            "quotes_json": json.dumps(quotes, ensure_ascii=False),
            "status": "DECIDING_LOWEST",
            "latest_step": f"WAITING_QUOTES→DECIDING_LOWEST(all_replied={all_replied}, deadline_hit={bool(deadline_ts and now_ts >= deadline_ts)})",
        })
        return True

    # 还没到点/未全部回：更新 quotes_json 后继续等
    _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
        "quotes_json": json.dumps(quotes, ensure_ascii=False),
        "latest_step": f"WAITING_QUOTES({len(quotes)} quotes so far)",
    })
    return False


def _parse_quote_body(body: str) -> dict:
    """从供应商报价正文抽单价/成色/数量/发货时间（正则，失败留空）。"""
    out = {}
    m = re.search(r"(?:单价|报价|含税价|价格)\s*[:：]?\s*[¥￥$]?\s*(\d+(?:\.\d+)?)", body)
    if m: out["unit_price"] = float(m.group(1))
    m = re.search(r"(成色|新旧)\s*[:：]?\s*(全新|原厂翻新|拆机二手|二手|全新原装)", body)
    if m: out["condition"] = m.group(1)
    m = re.search(r"(?:数量|订货量)\s*[:：]?\s*(\d+)", body)
    if m: out["count"] = int(m.group(1))
    m = re.search(r"(?:发货(?:时间|周期)?|交货(?:时间|周期)?|到货)\s*[:：]?\s*([\d\u4e00-\w\s]+?(?:天|日|周|小时内?)|\d{4}[-/]\d{1,2}[-/]\d{1,2})", body)
    if m: out["ship_time"] = m.group(1).strip()
    return out


def _step_deciding_lowest(task: dict, cfg: dict, tpls: dict):
    """DECIDING_LOWEST：算最低价 → 组模板 D 回复模板 A 会话 + 抄送审批人 → WAITING_APPROVAL；
    无有效报价 → 模板 F 中止 → DONE。"""
    tid = task["task_id"]
    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    tpl_d = (tpls or {}).get("D", {}) or {}
    tpl_f = (tpls or {}).get("F", {}) or {}
    approvers = list((cfg or {}).get("approver_emails") or [])

    # 过滤有效报价（不是迟到、单价可解析）
    valid = [q for q in quotes if not q.get("is_late") and q.get("unit_price") not in ("", None)]

    spm = _ensure_mail_inquiry_imports._spm

    if not valid:
        # 中止：模板 F，回复模板 A 会话
        reason = "无有效报价（全部迟到或供应商未回复）" if quotes else "无供应商回复"
        fmt_args = dict(
            project_no=task.get("project_no", ""),
            project_name=task.get("project_name", ""),
            part_type=task.get("part_type", ""),
            brand=task.get("brand", ""),
            pn=task.get("pn", ""),
            stop_reason=reason,
            task_no=tid,
        )
        body = _safe_format(tpl_f.get("body") or "", fmt_args)
        subj = _safe_format(tpl_f.get("subject") or "", fmt_args)
        tool_send_mail(to=[str(cfg.get("proc_mail_username") or "").strip()],
                       subject=subj, body_text=body,
                       reply_to_mail_id=task.get("thread_msg_id") or None)
        spm.spare_mail_update_task(tid, {
            "status": "DONE", "latest_step": "ABORT_NO_QUOTE",
            "lowest_supplier": "", "lowest_quote": "",
        })
        return True

    # 最低价
    valid.sort(key=lambda q: float(q.get("unit_price") or 1e18))
    lowest = valid[0]

    # 组模板 D：展示全部有效报价 + 系统提示最低价
    suppliers_str = "\n".join(
        f"  - {q.get('supplier','')} <{q.get('email','')}>：¥{q.get('unit_price','')} "
        f"{q.get('condition','')} x{q.get('count','')} / 发货 {q.get('ship_time','')}"
        for q in valid
    )
    lowest_quote_str = f"¥{lowest.get('unit_price','')}"
    lowest_supplier = lowest.get("supplier", "")

    body_d = (tpl_d.get("body") or "").format(
        project_no=task.get("project_no", ""),
        project_name=task.get("project_name", ""),
        part_type=task.get("part_type", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        spec=task.get("spec", ""),
        condition=task.get("condition", ""),
        count=task.get("count", ""),
        deadline=task.get("inquiry_deadline", ""),
        suppliers_count=len(valid),
        suppliers=suppliers_str,
        lowest_quote=lowest_quote_str,
        lowest_supplier=lowest_supplier,
        approver_emails="、".join(approvers) if approvers else "（未配置审批人）",
        task_no=tid,
    )
    subj_d = (tpl_d.get("subject") or "").format(
        project_no=task.get("project_no", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        suppliers_count=len(valid),
    )
    # 回复模板 A 会话 + 抄送审批人
    tool_send_mail(
        to=[str(cfg.get("proc_mail_username") or "").strip()],
        subject=subj_d, body_text=body_d,
        cc=approvers if approvers else None,
        reply_to_mail_id=task.get("thread_msg_id") or None,
    )

    spm.spare_mail_update_task(tid, {
        "lowest_supplier": lowest_supplier,
        "lowest_quote": json.dumps(lowest, ensure_ascii=False),
        "approval_state": "pending",
        "approval_result": "",
        "status": "WAITING_APPROVAL",
        "latest_step": f"DECIDING_LOWEST→WAITING_APPROVAL(lowest={lowest_supplier}@{lowest_quote_str})",
    })
    return True


def _step_waiting_approval(task: dict, cfg: dict, tpls: dict):
    """WAITING_APPROVAL：读模板 D 会话的后续回复 → 只有 approver_emails 白名单的回复才解析。

    分支：
      - 含"全部报价不可选/终止" → DONE + ABORT_ALL_REJECTED
      - 含"确认采购" + 指定供应商 → target_supplier 为指定 → ORDERING
      - 含"确认采购" + 无供应商 → target_supplier = lowest_supplier → ORDERING
      - 未命中任何关键字 → 继续 WAITING_APPROVAL
    """
    tid = task["task_id"]
    approvers = [str(e).lower().strip() for e in (cfg or {}).get("approver_emails") or [] if e]
    lowest_supplier = task.get("lowest_supplier", "")
    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    tpl_f = (tpls or {}).get("F", {}) or {}

    if not approvers:
        # 未配置审批人 → 直接选最低价进 ORDERING（自动通过）
        _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
            "target_supplier": lowest_supplier,
            "approval_state": "auto_approved",
            "approval_result": "no_approver_configured",
            "status": "ORDERING",
            "latest_step": f"WAITING_APPROVAL→ORDERING(auto, target={lowest_supplier})",
        })
        return True

    # 拉邮件：模板 D 发出去的 Message-ID 没存，用 thread_msg_id（模板 A 的）
    # 匹配回复——In-Reply-To 链条最终会 reference 到模板 A 的 message_id
    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60 * 2
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = tool_read_inbox_mail(since_timestamp=since_ts, exclude_sender_email_list=exclude,
                             match_in_reply_to_msg_ids=[_norm_mid(task.get("thread_msg_id", ""))])
    if not r.get("success"):
        return False

    spm = _ensure_mail_inquiry_imports._spm
    for m in r.get("mails", []):
        from_email = str(m.get("from_email") or "").lower().strip()
        if from_email not in approvers:
            continue  # 忽略非审批人

        body = (m.get("mail_body_text") or "") + "\n" + (m.get("subject") or "")
        # 分支 1: 全部不可选/终止
        if re.search(r"全部报价不可选|全部不可选|任务终止|终止询价|全部拒绝", body):
            fmt_args = dict(
                project_no=task.get("project_no", ""),
                project_name=task.get("project_name", ""),
                part_type=task.get("part_type", ""),
                brand=task.get("brand", ""),
                pn=task.get("pn", ""),
                stop_reason="审批人全部拒绝：全部报价不可选",
                task_no=tid,
            )
            body_f = _safe_format(tpl_f.get("body") or "", fmt_args)
            subj_f = _safe_format(tpl_f.get("subject") or "", fmt_args)
            tool_send_mail(to=[str(cfg.get("proc_mail_username") or "").strip()],
                           subject=subj_f, body_text=body_f,
                           reply_to_mail_id=task.get("thread_msg_id") or None)
            spm.spare_mail_update_task(tid, {
                "approval_state": "rejected",
                "approval_result": "ALL_REJECTED",
                "status": "DONE",
                "latest_step": "WAITING_APPROVAL→ABORT_ALL_REJECTED",
            })
            return True

        # 分支 2 & 3: 确认采购
        if re.search(r"确认采购|同意采购|批准采购|确认订货|批准订货|采购通过", body):
            # 看有没有指定供应商（从 quotes 里按名称匹配）
            specified_supplier = ""
            valid_supplier_names = [q.get("supplier", "") for q in quotes if not q.get("is_late")]
            for sname in valid_supplier_names:
                if sname and sname in body:
                    specified_supplier = sname
                    break

            target = specified_supplier or lowest_supplier
            result_label = f"指定供应商:{target}" if specified_supplier else f"沿用最低价:{lowest_supplier}"
            spm.spare_mail_update_task(tid, {
                "target_supplier": target,
                "approval_state": "approved",
                "approval_result": result_label,
                "status": "ORDERING",
                "latest_step": f"WAITING_APPROVAL→ORDERING({result_label})",
            })
            return True

    # 还没找到审批人回复 → 继续等
    spm.spare_mail_update_task(tid, {
        "latest_step": "WAITING_APPROVAL(waiting_for_approver_reply)",
    })
    return False


def _step_ordering(task: dict, cfg: dict, tpls: dict):
    """ORDERING：定位 target_supplier 的报价邮件 Message-ID → 渲染模板 E（回复该报价会话）→ 带收货地址 → DONE。"""
    tid = task["task_id"]
    tpl_e = (tpls or {}).get("E", {}) or {}
    target = task.get("target_supplier", "")
    if not target:
        _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
            "status": "DONE", "latest_step": "ORDERING_SKIPPED_NO_TARGET",
        })
        return False

    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    target_quote = next((q for q in quotes if q.get("supplier") == target), None)
    target_email = (target_quote or {}).get("email", "") if target_quote else ""
    reply_mid = _norm_mid((target_quote or {}).get("msg_id", "")) if target_quote else ""
    if not target_email and target_quote:
        target_email = next(
            (s.get("email", "") for s in _safe_json_loads(task.get("suppliers_json") or "[]")
             if s.get("name") == target),
            "")

    latest_ship_time = task.get("latest_ship_time") or datetime.now().strftime("%Y-%m-%d")
    condition_display_map = {
        "全新": "全新原装", "原厂翻新": "原厂翻新（带保修）", "拆机二手": "拆机二手（无保修）",
    }
    cond_display = condition_display_map.get(task.get("condition", ""), task.get("condition", ""))
    address = task.get("address") or "（收货地址未填，请回复本会话确认）"

    body = (tpl_e.get("body") or "").format(
        supplier=target,
        quote=(target_quote or {}).get("unit_price", "") or "",
        project_no=task.get("project_no", ""),
        project_name=task.get("project_name", ""),
        part_type=task.get("part_type", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        spec=task.get("spec", ""),
        condition=task.get("condition", ""),
        condition_display=cond_display,
        count=task.get("count", ""),
        address=address,
        receiver_name="运维部",
        receiver_phone="（请回复本会话提供）",
        latest_ship_time=latest_ship_time,
        task_no=tid,
    )
    subj = (tpl_e.get("subject") or "").format(
        project_no=task.get("project_no", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        count=task.get("count", ""),
    )

    mail_r = tool_send_mail(
        to=[target_email] if target_email else [str(cfg.get("proc_mail_username") or "").strip()],
        subject=subj, body_text=body,
        reply_to_mail_id=reply_mid or None,
    )

    _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
        "status": "DONE",
        "latest_step": f"ORDER_CONFIRMED(sent_to={target_email}, mail_ok={mail_r.get('success', False)})",
    })
    return True


# ════════════════════════════════════════════════════════════════
# 调试 / 管理端点（不新增 config 表、不暴露敏感字段）
# ════════════════════════════════════════════════════════════════

@router.get("/mail-inquiry/tasks")
async def mail_inquiry_tasks(status: str = "", keyword: str = "", page_size: int = 100):
    """备件邮件询价任务列表（简版）。status 过滤可选。"""
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    spm = _ensure_mail_inquiry_imports._spm
    r = spm.spare_mail_list_tasks(filter={"status": status, "keyword": keyword}, page_size=page_size)
    # 返回时剥掉 raw_body 等大字段
    safe = []
    for t in r:
        safe.append({k: v for k, v in t.items() if k not in ("raw_body",)})
    return {"success": True, "total": len(safe), "tasks": safe}


@router.get("/mail-inquiry/task/{task_id}")
async def mail_inquiry_task_detail(task_id: str):
    """单任务详情。"""
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    spm = _ensure_mail_inquiry_imports._spm
    t = spm.spare_mail_get_task(task_id)
    if not t:
        return {"success": False, "error": "not_found"}
    return {"success": True, "task": t}


@router.post("/mail-inquiry/tick")
async def mail_inquiry_manual_tick():
    """手动强制触发一次 tick（测试/调试用）。"""
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    return {"success": True, "result": tick_mail_inquiry()}


@router.post("/mail-inquiry/register")
async def mail_inquiry_register_employee():
    """幂等注册「备件邮件询价数字员工」。启动时或调试时调用均可。"""
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    emp_id = "emp-mail-inquiry"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emp = {
        "id": emp_id,
        "name": "备件邮件询价数字员工",
        "desc": "由 scheduler/tick?kind=mail-inquiry 驱动的备件邮件询价流程引擎，覆盖邮件抓取、供应商询价、报价汇总、内部审批、下达订货全流程。",
        "type": "digital_employee",
        "created": now_str,
        "updated": now_str,
        "rag_kb": "",
        "prompt": "你是备件邮件询价数字员工，负责从工程师询价邮件中抽取字段、自动向供应商发询价邮件、汇总报价并推送内部审批、最终下达订货邮件。",
        "model": "",
        "skills": [_SKILL_ID_MAIL_INQUIRY],
        "skill_states": {_SKILL_ID_MAIL_INQUIRY: True},
        "enabled": True,
    }
    _ensure_mail_inquiry_imports._upsert_emp(emp)
    return {"success": True, "employee_id": emp_id, "skill_id": _SKILL_ID_MAIL_INQUIRY}
