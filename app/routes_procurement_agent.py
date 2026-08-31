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
    # ── 备件属性：页面入口由 9006 传入，邮件入口由 _extract_inquiry_fields 解析填充。
    # 缺这些字段时模板 B 的变量取不到值，只能回退 LLM 组邮件（标题会失控）。
    project_no: str = ""
    part_type: str = ""
    brand: str = ""
    pn: str = ""
    spec: str = ""
    condition: str = ""
    address: str = ""
    urgent: str = ""
    latest_ship_time: str = ""
    # ── 双流 / 三入口 ──
    source: str = ""
    internal_status: str = ""
    external_status: str = ""

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


def _load_inquiry_template_b() -> dict:
    """取模板 B（对外询价）。优先运行时配置 proc_templates，回退 skill JSON。"""
    try:
        spm = _ensure_mail_inquiry_imports._spm
        tpls = spm.spare_mail_get_config("proc_templates") or {}
        if isinstance(tpls, dict) and (tpls.get("B") or {}).get("subject"):
            return tpls["B"]
    except Exception:
        pass
    try:
        from app.skill_loader import load_skill
        sk = load_skill("skill-proc-mail-inquiry") or {}
        return ((sk.get("templates") or {}).get("B") or {})
    except Exception:
        return {}


def _build_inquiry_tpl_ctx(task, ctx: dict) -> dict:
    """把 flow-02 的上下文映射成模板 B 的变量名。

    模板 B 用的是 {brand} / {pn} / {count} / {task_no} / {urgent} / {supplier}，
    而 _build_inquiry_ctx 产出的是 part_brand / purchase_qty / task_id，
    两者命名不一致，历史上导致模板根本用不起来（只能靠 LLM 自由发挥）。
    """
    def g(k, default=""):
        return str(getattr(task, k, "") or default)

    def fmt_count(v):
        """数量去掉无意义的 .0（purchase_qty 是 float，2.0 应显示成 2）"""
        try:
            f = float(v)
            return str(int(f)) if f == int(f) else str(f)
        except Exception:
            return str(v or "")

    return {
        # part_type 兜底 spare_part_model：9006 的 create_task 未把 part_type 落库，
        # 缺失会导致模板 B 变量不全而整个回退到 LLM。
        "part_type": ctx.get("part_type") or g("part_type") or g("spare_part_model"),
        "brand": ctx.get("part_brand") or g("brand"),
        "pn": ctx.get("part_pn") or g("pn"),
        "spec": ctx.get("part_spec") or g("spec"),
        "condition": ctx.get("part_condition") or g("condition"),
        "count": fmt_count(ctx.get("purchase_qty") or g("purchase_qty")),
        "urgent": g("urgent") or g("emergency_level"),
        "latest_ship_time": g("latest_ship_time"),
        "deadline": ctx.get("reply_deadline") or "",
        "project_no": g("project_no") or ctx.get("contract_no", ""),
        "project_name": ctx.get("project_name") or g("project_name"),
        "task_no": ctx.get("task_id") or g("task_id"),
        "supplier": "",  # 逐供应商渲染时填入
    }


def _tpl_ready(tpl: dict, ctx: dict) -> bool:
    """模板所需变量是否齐全（{supplier} 例外，它按供应商逐个填充）。"""
    import re as _re
    text = (tpl.get("subject") or "") + "\n" + (tpl.get("body") or "")
    need = {v for v in _re.findall(r"\{(\w+)\}", text)}
    need.discard("supplier")
    return all(str(ctx.get(k) or "").strip() for k in need)


def _send_inquiry_by_template(inq_list, tpl: dict, base_ctx: dict, cc) -> dict:
    """按模板 B 逐供应商渲染并发送（模板含 {supplier}，无法用同一封群发）。

    返回结构与 tool_batch_send_mail 一致，保证下游 _sent_msg_id 回写逻辑不变。
    """
    sent, failed = [], []
    for s in inq_list:
        c2 = dict(base_ctx)
        c2["supplier"] = str(getattr(s, "name", "") or getattr(s, "email", "") or "")
        subj = _safe_format(tpl.get("subject") or "", c2)
        body = _safe_format(tpl.get("body") or "", c2)
        try:
            r = tool_send_mail(to=[s.email], subject=subj, body_text=body, cc=cc or None) or {}
        except Exception as e:
            r = {"success": False, "error": f"{type(e).__name__}: {e}"}
        item = {"email": s.email, "message_id": str(r.get("message_id") or ""), "subject": subj}
        if r.get("success") and r.get("message_id"):
            sent.append(item)
        else:
            item["error"] = r.get("error") or "未返回邮件 ID"
            failed.append(item)
    return {"tool": "send_mail_by_template", "success": not failed,
            "total_count": len(inq_list), "success_count": len(sent),
            "fail_email_list": failed, "sent": sent}


def _flow_proc_02_send_inquiry_mail(task: TaskInstance) -> dict:
    """LLM 组装&发送询价邮件 + 飞书通知项目经理任务已发起
    邮件组装由 skill-proc-mail-compose（LLM）完成，失败时自动降级到硬编码模板
    【修复】发送后给 inquiry_supplier_list 每一项回写 _sent_msg_id，用于 flow-03 按
    In-Reply-To/References 匹配供应商回复，避免 1 个供应商邮箱对应多个任务时串任务。
    """
    ctx = _build_inquiry_ctx(task)
    # 模板优先：模板 B 所需变量齐全时直接按模板渲染，LLM 只在变量不足时兜底。
    # 背景：LLM 自由发挥曾产出「SMOKE-xxx（）-电池模块型号备件询价邮件」这类
    # 不受模板约束的标题（模板变量为空被渲染成空括号）。
    tpl_ctx = _build_inquiry_tpl_ctx(task, ctx)
    tpl_b = _load_inquiry_template_b()
    use_template = bool(tpl_b and _tpl_ready(tpl_b, tpl_ctx))
    if use_template:
        mail_content = {"subject": _safe_format(tpl_b.get("subject") or "", tpl_ctx),
                        "body_text": _safe_format(tpl_b.get("body") or "", tpl_ctx),
                        "composed_by": "template"}
    else:
        mail_content = invoke_skill_mail_compose("inquiry", ctx)
    subject = mail_content.get("subject") or ""
    body = mail_content.get("body_text") or ""

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
    if use_template:
        # 模板含 {supplier}，需按供应商逐封渲染（batch 只能发同一份内容）
        mail_r = _send_inquiry_by_template(inq_list, tpl_b, tpl_ctx, global_cc)
    else:
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
    try:
        from app.mcp_tools import _proc_mail_cfg as _pmc
        _pc = _pmc()
        mail_configured = bool(_pc.get("mail_password"))
        feishu_configured = bool(_pc.get("feishu_app_id") and _pc.get("feishu_app_secret"))
        feishu_pm = bool(_pc.get("feishu_pm_open_id"))
        bitable = bool(_pc.get("feishu_bitable_app_token"))
    except Exception:
        _pc = {}
        mail_configured = bool(config.PROC_MAIL_PASSWORD)
        feishu_configured = bool(config.PROC_FEISHU_APP_ID and config.PROC_FEISHU_APP_SECRET)
        feishu_pm = bool(config.PROC_FEISHU_PM_OPEN_ID)
        bitable = bool(config.PROC_FEISHU_BITABLE_APP_TOKEN)
    return {
        "success": True,
        "employee": "emp-008",
        "name": "备品备件采购询比价专员",
        "mail_configured": mail_configured,
        "feishu_configured": feishu_configured,
        "feishu_pm_open_id_configured": feishu_pm,
        "bitable_configured": bitable,
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
    try:
        from app.db import spare_mail as _spm; _ensure_mail_inquiry_imports._spm = _spm
        from app.db.schema import init_spare_mail_db as _init_db; _ensure_mail_inquiry_imports._init_db = _init_db
        from app.db.employees import db_upsert_employee as _upsert_emp; _ensure_mail_inquiry_imports._upsert_emp = _upsert_emp
        from app.skill_loader import load_skill as _load_sk; _ensure_mail_inquiry_imports._load_sk = _load_sk
        from app.db.contract_mail import contract_mail_archive_append as _arc; _ensure_mail_inquiry_imports._arc = _arc
    except Exception as e:
        raise RuntimeError(f"mail-inquiry imports failed: {e}")


# ── 常量 ──
_SKILL_ID_MAIL_INQUIRY = "skill-proc-mail-inquiry"
_TICK_MAX_TASKS = 5          # 每 tick 最多推进 N 个任务
_DEFAULT_SINCE_MINUTES = 120  # 读邮件窗口（2h）
_INTERNAL_KEYWORDS = ("备件", "询价", "采购", "备件询价", "备件采购")


def _archive_sent_mail(tid: str, kind: str, mail_r) -> None:
    """把一封系统发出的关键邮件原文归档到 mail_archive_json，供页面查看历史原文/To/Cc。"""
    if not mail_r or not isinstance(mail_r, dict):
        return
    _ensure_mail_inquiry_imports()
    try:
        _ensure_mail_inquiry_imports._arc(tid, {
            "kind": kind,
            "flow": "external" if kind in ("B", "C", "E", "G") else "internal",
            "msg_id": mail_r.get("message_id", "") or "",
            "subject": mail_r.get("subject", "") or "",
            "to": mail_r.get("to") or [],
            "cc": mail_r.get("cc") or [],
            "reply_to": mail_r.get("reply_to", "") or "",
            "refs": mail_r.get("refs_chain", "") or "",
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception as e:
        print(f"[mail-inquiry] archive_sent_mail failed: {e}")


def _external_flow_cc(task: dict, cfg: dict, exclude_to=(), extra_cc=()) -> list:
    """外部流(E订货/G结算)的抄送名单：审批人 + 全局系统抄送 + 工程师 + 工程师询价邮件收/抄送人 + 供应商报价邮件抄送人。

    exclude_to 为收件人(To)，在抄送里剔除，避免重复。始终排除自身(智能体)。
    extra_cc 为被回复的供应商报价邮件所携带的抄送地址（追加进去，满足"给供应商回复带其抄送"）。
    """
    cc, seen = [], set()
    def _add(e):
        e = str(e or "").strip()
        if e and "@" in e and e not in seen:
            seen.add(e); cc.append(e)
    for e in (cfg or {}).get("approver_emails") or []:
        _add(e)
    for e in (_fetch_global_cc_list() or []):
        _add(e)
    eng = (task.get("from_email") or "").strip()
    if eng and "@" in eng:
        _add(eng)
    try:
        ito = json.loads(task.get("inquiry_to_json") or "[]")
        icc = json.loads(task.get("inquiry_cc_json") or "[]")
    except Exception:
        ito, icc = [], []
    for e in list(ito) + list(icc):
        _add(e)
    for e in (extra_cc or []):
        _add(e)
    self_e = str((cfg or {}).get("proc_mail_username") or "").strip().lower()
    exclude_low = {str(x).strip().lower() for x in (exclude_to or []) if x}
    out = [e for e in cc
           if not (self_e and e.lower() == self_e)
           and e.lower() not in exclude_low]
    return out


def _task_neu_no(task: dict) -> str:
    """生成任务号：NEU + 项目号后四位 + 创建时间(精确到分钟)，如 NEU3465202608311021。

    仅作为邮件标题/正文里的外部任务标识（工程师初始邮件 A 除外，不带任务号）。
    """
    pno = str((task or {}).get("project_no") or "")
    last4 = pno[-4:] if len(pno) >= 4 else pno
    ctime = str((task or {}).get("created_at") or "")[:16]  # YYYY-MM-DD HH:MM
    digits = "".join(ch for ch in ctime if ch.isdigit())
    if len(digits) < 12:
        digits = datetime.now().strftime("%Y%m%d%H%M")
    return f"NEU{last4}{digits}"

# ── tick 级 IMAP 缓存：每次 tick 开头做一次 UNSEEN 拉取，后续 step 函数复用 ──
# 避免每任务一次 IMAP SEARCH，10 个任务从 10 次缩到 1 次
_TICK_UNSEEN_CACHE = None


def _tick_prefetch_unseen(cfg: dict):
    """tick 开头调用一次：拉取 UNSEEN 邮件存入模块级缓存，后续 step 复用。"""
    global _TICK_UNSEEN_CACHE
    _TICK_UNSEEN_CACHE = None
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    try:
        _TICK_UNSEEN_CACHE = tool_read_inbox_mail(use_unseen=True,
                                                  exclude_sender_email_list=exclude)
        n = len((_TICK_UNSEEN_CACHE or {}).get("mails", []))
        print(f"[mail-inquiry tick] UNSEEN cache: {n} mails pre-fetched")
        # 如果 UNSEEN 返回 0 封（163 IMAP UNSEEN 搜索不稳定时），清缓存让后续 step 回退全量拉取
        if n == 0:
            _TICK_UNSEEN_CACHE = None
            print(f"[mail-inquiry tick] UNSEEN 0 → fallback 全量拉取")
    except Exception as e:
        print(f"[mail-inquiry tick] UNSEEN pre-fetch failed: {e}")
        _TICK_UNSEEN_CACHE = None


def _tick_cached_read_inbox(since_timestamp: int = 0, exclude_sender_email_list: list = None,
                            match_in_reply_to_msg_ids: list = None,
                            filter_sender_email_list: list = None,
                            force_refresh: bool = False) -> dict:
    """优先用 tick 级 UNSEEN 缓存过滤邮件，缓存为空时 fallback 到真实 IMAP。

    过滤逻辑完全对齐 tool_read_inbox_mail：黑名单排除、match_ids 命中、发件人白名单。
    """
    global _TICK_UNSEEN_CACHE
    if force_refresh or not _TICK_UNSEEN_CACHE or not _TICK_UNSEEN_CACHE.get("success"):
        # 没有缓存 → 真实 IMAP 拉取
        return tool_read_inbox_mail(since_timestamp=since_timestamp,
                                    exclude_sender_email_list=exclude_sender_email_list,
                                    match_in_reply_to_msg_ids=match_in_reply_to_msg_ids,
                                    filter_sender_email_list=filter_sender_email_list)

    # 有缓存 → 内存过滤
    exclude_set = {str(e).lower().strip() for e in (exclude_sender_email_list or []) if e}
    match_set = {_norm_mid(m) for m in (match_in_reply_to_msg_ids or []) if m}
    filtered = []
    for m in _TICK_UNSEEN_CACHE.get("mails", []):
        # 黑名单
        if str(m.get("from_email") or "").lower() in exclude_set:
            continue
        # 发件人白名单
        if filter_sender_email_list:
            if str(m.get("from_email") or "").lower() not in [str(e).lower().strip() for e in filter_sender_email_list]:
                continue
        # 线程匹配
        if match_set:
            hit = False
            for raw_ref in [m.get("in_reply_to", ""), m.get("references", "")]:
                if raw_ref:
                    for part in re.split(r"\s+", str(raw_ref).strip()):
                        if _norm_mid(part) in match_set:
                            hit = True
                            break
                if hit:
                    break
            if not hit:
                continue
        filtered.append(m)

    return {"tool": "cached_read_inbox", "success": True, "total": len(filtered), "mails": filtered}

# ── 工具函数 ──
def _norm_mid(m):
    """规范化 RFC Message-ID（去掉前后 <>）。"""
    s = str(m or "").strip()
    while s.startswith("<"): s = s[1:]
    while s.endswith(">"):   s = s[:-1]
    return s.strip()


def _fetch_sent_mail_refs(target_msg_id: str) -> str:
    """IMAP fetch 我方邮箱 Sent Messages 文件夹，按 Message-ID 找指定邮件，
    返回其 References 头（邮箱权威，不再用 DB 存的 refs 链）。
    找不到返回空串（fallback 到调用方兜底逻辑）。"""
    mid = _norm_mid(target_msg_id)
    if not mid:
        return ""
    try:
        import imaplib, email as _em, os as _os
        from email.header import decode_header as _dh

        cfg = _proc_mail_cfg()
        user = str(cfg.get("mail_username") or "").strip()
        pwd = str(cfg.get("mail_password") or "").strip()
        if not user or not pwd:
            return ""

        imap = imaplib.IMAP4_SSL("imap.163.com", 993)
        imap.login(user, pwd)
        imaplib.Commands["ID"] = ("AUTH",)
        try:
            imap._simple_command("ID", '("name" "NeuOps" "vendor" "NeuOps")')
        except Exception:
            pass
        # 163 免费版 Sent 文件夹实际名是 "Sent Messages"
        for folder in ['"Sent Messages"', 'Sent Messages']:
            try:
                ok, _ = imap.select(folder, readonly=True)
                if ok != "OK":
                    continue
                _, data = imap.search(None, "ALL")
                for num in reversed((data[0] or b"").split()[-50:]):  # 只查最近 50 封
                    _, d = imap.fetch(num, "(RFC822)")
                    if not d or not d[0]:
                        continue
                    msg = _em.message_from_bytes(d[0][1])
                    if _norm_mid(msg.get("Message-ID", "")) == mid:
                        refs = msg.get("References", "") or ""
                        imap.logout()
                        return refs.strip()
            except Exception:
                continue
        try:
            imap.logout()
        except Exception:
            pass
    except Exception as e:
        print(f"[_fetch_sent_mail_refs] IMAP error: {e}")
    return ""


def _quote_orig_body(body: str, max_chars: int = 3000) -> str:
    """将邮件正文以清晰的引用分隔符追加到回复末尾。

    用纯文本分隔线（--- / =）包裹原文，比 `>` 前缀在 webmail 客户端里渲染更稳定。
    截断过长原文，避免线程链越来越臃肿。
    """
    body = str(body or "").strip()
    if not body:
        return ""
    # 跳过已被引用的旧内容（避免无限嵌套）
    lines = [ln for ln in body.splitlines()
             if not ln.strip().startswith(">") and not ln.strip().startswith("---")
             and "原始邮件" not in ln]
    content = "\n".join(lines).strip()
    if not content:
        return ""
    if len(content) > max_chars:
        content = content[:max_chars] + "\n……（引用过长已截断）"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"\n\n{'=' * 40}\n【引用】以下为 {ts} 的被回复邮件原文\n{'=' * 40}\n{content}\n{'=' * 40}\n"

def _load_mail_inquiry_skill():
    """加载 mail-inquiry 配置：以 skill JSON 为底，spare_mail_config（DB）优先覆盖。

    返回 (config_dict, templates_dict)。
    - config 优先 DB `proc_participants` + `proc_credentials` 合并，缺失回退 skill.config
    - templates 优先 DB `proc_templates`，缺失回退 skill.templates
    失败时返回 (None, None)。
    """
    try:
        _ensure_mail_inquiry_imports()
        sk = _ensure_mail_inquiry_imports._load_sk(_SKILL_ID_MAIL_INQUIRY)
        skill_def = (sk or {}).get("skill") or {}
        cfg = skill_def.get("config") or {}
        tpls = skill_def.get("templates") or {}

        spm = _ensure_mail_inquiry_imports._spm
        # 参与方（审批人/供应商）
        p = spm.spare_mail_get_config("proc_participants") or {}
        if isinstance(p, dict):
            if p.get("approver_emails") not in (None, []):
                cfg["approver_emails"] = p["approver_emails"]
            if p.get("default_suppliers") not in (None, []):
                cfg["default_suppliers"] = p["default_suppliers"]
        # 邮件凭据（供 health / 提示用）
        cred = spm.spare_mail_get_config("proc_credentials") or {}
        if isinstance(cred, dict):
            if cred.get("mail_username") not in (None, ""):
                cfg["proc_mail_username"] = cred["mail_username"]
        # 模板
        db_tpls = spm.spare_mail_get_config("proc_templates") or {}
        if isinstance(db_tpls, dict) and db_tpls:
            merged = dict(tpls)
            merged.update({k: v for k, v in db_tpls.items() if v})
            tpls = merged
        return cfg, tpls
    except Exception as e:
        print(f"[mail-inquiry] load skill failed: {e}")
        return None, None

def _gen_task_id() -> str:
    """生成 MI-{timestamp}-{rand6} 格式的任务号。"""
    import random
    ts = int(time.time())
    r = ''.join(random.choices('abcdef0123456789', k=6))
    return f"MI-{ts}-{r}"

def _urgent_to_seconds(urgent: str) -> int:
    """紧急程度字符串 → 秒。支持 5min/1h/24小时/3天。解析失败默认 24h。"""
    s = str(urgent or "").strip().lower().replace(" ", "")
    m = re.match(r"(\d+)\s*(分钟|min|m|小时|h|天|d)", s)
    if not m:
        return 24 * 3600
    n = int(m.group(1)); unit = m.group(2)
    if unit in ("分钟", "min", "m"):
        return n * 60
    if unit in ("小时", "h"):
        return n * 3600
    if unit in ("天", "d"):
        return n * 24 * 3600
    return n * 3600

def _mail_date_ts(mail: dict) -> int:
    """从邮件头 Date 字段取发送方声明时间；缺失时回退 receive_timestamp / now。"""
    d = (mail or {}).get("date") or (mail or {}).get("date_raw") or ""
    if d:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(d)
            if dt.tzinfo is None:
                import datetime as _dt
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return int(dt.timestamp())
        except Exception:
            pass
    ts = int((mail or {}).get("receive_timestamp") or 0)
    return ts or int(time.time())

def _inquiry_deadline(mail: dict, urgent: str) -> str:
    """报价截止时间 = 邮件头 Date（发送时间）+ 紧急时长。返回 '%Y-%m-%d %H:%M:%S'。"""
    base_ts = _mail_date_ts(mail)
    secs = _urgent_to_seconds(urgent)
    return datetime.fromtimestamp(base_ts + secs).strftime("%Y-%m-%d %H:%M:%S")

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


# ── 主循环：tick_mail_inquiry（双邮件流：internal_status + external_status）──
def tick_mail_inquiry():
    """每次被 scheduler/tick?kind=mail-inquiry 调用时执行。

    双邮件流模型：
    - 内部流（internal_status）：工程师询价线程 —— R_INIT→R_APPROVAL→R_CLOSED
        R_INIT：报价就绪后发模板 D 汇总（抄送审批人）
        R_APPROVAL：识别审批人确认/拒绝 与 工程师"备件更换完成"回执
        R_CLOSED：工程师回执后对外发模板 G 结算邮件 → 终态 DONE
    - 外部流（external_status）：智能体↔供应商 —— R_SEND→R_WAIT_QUOTES→R_DECIDING
        →R_ORDER→R_WAIT_SHIPPING→R_WAIT_ACCEPTANCE→R_WAIT_SETTLE
        R_SEND：发模板 B 询价
        R_WAIT_QUOTES：收报价
        R_DECIDING：算最低价 + 未选中供应商标记截止
        R_ORDER：审批确认后发模板 E 订货
        R_WAIT_SHIPPING：等选中供应商回快递单号
        R_WAIT_ACCEPTANCE：供应商已发货、收货待测试（采购确认）——等工程师验收回执
        R_WAIT_SETTLE：工程师验收通过 → 已通知供应商结算、等待结算（终态）
    每条流各自按状态推进；每个任务独立 try/except，单任务异常不阻塞其它。
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
    step_stats = {"parsing": {}, "internal": {}, "external": {}}
    spm = _ensure_mail_inquiry_imports._spm

    # ── 【UNSEEN 增量优化】开头一次拉取全部 UNSEEN，后续 step 复用缓存，避免每任务一次 IMAP SEARCH ──
    _tick_prefetch_unseen(cfg)

    # ── 抓取"工程师发起询价"邮件并落任务（两条流之源头）──
    try:
        parsed = _step_parsing(cfg, tpls)
        step_stats["parsing"] = parsed
        progress += parsed.get("created", 0)
    except Exception as e:
        step_stats["parsing"] = {"error": str(e)}

    # 一次拉取活动任务，按 internal_status / external_status 在内存里分流
    try:
        tasks = spm.spare_mail_list_tasks(page_size=2000)
    except Exception as e:
        tasks = []
        step_stats["list"] = {"error": str(e)}
        return {"enabled": True, "progress": progress, "step_stats": step_stats}

    _INTERNAL_STATES = {"R_INIT", "R_APPROVAL"}
    _EXTERNAL_STATES = {"R_SEND", "R_WAIT_QUOTES", "R_DECIDING", "R_ORDER", "R_WAIT_SHIPPING",
                        "R_WAIT_ACCEPTANCE", "R_WAIT_SETTLE"}
    # legacy 别名：老 status 名 → 双流维度下的统计键（dashboard/测试兼容）
    _LEGACY = {
        "R_SEND": "SENDING_B", "R_WAIT_QUOTES": "WAITING_QUOTES",
        "R_DECIDING": "DECIDING_LOWEST", "R_APPROVAL": "WAITING_APPROVAL",
        "R_ORDER": "ORDERING", "R_WAIT_SHIPPING": "SHIPPING",
        "R_WAIT_ACCEPTANCE": "WAITING_ACCEPTANCE", "R_WAIT_SETTLE": "WAITING_SETTLE",
    }

    # ── 内部流：按 internal_status 推进 ──
    int_scanned = 0
    int_processed = 0
    int_legacy_cnt = {}
    for t in tasks:
        st = t.get("internal_status") or ""
        if st not in _INTERNAL_STATES:
            continue
        if int_processed >= _TICK_MAX_TASKS:
            break
        int_scanned += 1
        try:
            if _mi_step_internal(t, cfg, tpls):
                progress += 1
                int_processed += 1
                int_legacy_cnt[st] = int_legacy_cnt.get(st, 0) + 1
        except Exception as e:
            spm.spare_mail_update_task(t["task_id"], {"latest_step": f"INTERNAL_ERROR:{e}"})
    if int_scanned:
        step_stats["internal"] = {"scanned": int_scanned, "processed": int_processed,
                                  "by_status": int_legacy_cnt}

    # ── 外部流：按 external_status 推进 ──
    ext_scanned = 0
    ext_processed = 0
    ext_legacy_cnt = {}
    for t in tasks:
        st = t.get("external_status") or ""
        if st not in _EXTERNAL_STATES:
            continue
        if ext_processed >= _TICK_MAX_TASKS:
            break
        ext_scanned += 1
        try:
            if _mi_step_external(t, cfg, tpls):
                progress += 1
                ext_processed += 1
                ext_legacy_cnt[st] = ext_legacy_cnt.get(st, 0) + 1
        except Exception as e:
            spm.spare_mail_update_task(t["task_id"], {"latest_step": f"EXTERNAL_ERROR:{e}"})
    if ext_scanned:
        step_stats["external"] = {"scanned": ext_scanned, "processed": ext_processed,
                                  "by_status": ext_legacy_cnt}

    # legacy 别名（兼容旧 dashboard，避免直接破坏读取方）
    for st, cnt in int_legacy_cnt.items():
        if st in _LEGACY:
            step_stats[_LEGACY[st]] = {"processed": cnt}
    for st, cnt in ext_legacy_cnt.items():
        if st in _LEGACY:
            step_stats[_LEGACY[st]] = {"processed": cnt}

    return {"enabled": True, "progress": progress, "step_stats": step_stats}


# ════════════════════════════════════════════════════════════════
# Step 实现
# ════════════════════════════════════════════════════════════════

def _step_parsing(cfg, tpls):
    """PARSING 状态：读收件箱找工程师发起询价的内部邮件 → 建任务 → 转到 SENDING_B。"""
    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60
    # 黑名单：采购方自己的邮箱（排除 sent 副本）
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = _tick_cached_read_inbox(since_timestamp=since_ts, exclude_sender_email_list=exclude)
    created = 0
    if not r.get("success"):
        return {"created": 0, "msg": r.get("error", "read inbox failed")}

    # 已创建的线程集合（避免同一封初始询价邮件重复入库）
    _all_tasks = _ensure_mail_inquiry_imports._spm.spare_mail_list_tasks(page_size=2000)
    # 去重仅按"工程师初始询价邮件自身的 message-id"：同一封邮件重复扫描不重复建任务。
    # 不用项目号去重——同一项目会有多次采购，各自建独立任务（每个任务有自己的 NEU 任务号，
    # 工程师初始邮件尚无任务号，故以其邮件本身为唯一键，后续同任务邮件按线程 In-Reply-To/References 匹配）。
    existing_threads = {t.get("thread_msg_id", "") for t in _all_tasks if t.get("thread_msg_id")}

    for m in r.get("mails", []):
        body = (m.get("mail_body_text") or "")
        subject = (m.get("subject") or "")
        mid = _norm_mid(m.get("message_id", ""))
        if not mid or mid in existing_threads:
            continue

        # 排除条件：
        # 1) 邮件是回复邮件（in_reply_to 不为空）→ 跳过，不是工程师发起
        # 2) 主题以 Re: / 回复 / Re: 开头 → 跳过
        if m.get("in_reply_to") or m.get("references"):
            continue
        subj_lower = subject.lower()
        if subj_lower.startswith("re:") or subj_lower.startswith("回复") or subj_lower.startswith("re :"):
            continue

        # 命中关键词 → 判定为"工程师发起询价"邮件
        body_flat = re.sub(r"\s+", "", body + subject)
        if not any(kw in body_flat for kw in _INTERNAL_KEYWORDS):
            continue

        # 从正文抽取字段（尽量解析，不完整就留空由后续补）
        fields = _extract_inquiry_fields(body, subject)
        # 正则为主、LLM 兜底：关键字段（brand/pn/part_type/count/spec）缺失时调 DeepSeek 补抽
        if _extract_needs_llm(fields):
            fields = _llm_fallback_extract(body, subject, fields)

        # ── R-FR-02：必填字段校验 + 格式异常回信阻断（不建任务、不询价）──
        missing = [k for k in _MI_LLM_REQUIRED if not (fields.get(k) or "").strip()]
        if missing:
            _reply_missing_fields(m, missing, fields)
            # 持久化"已回信"标记：建一条 REJECTED 任务占用该 msg_id，
            # 使下次 tick 的 existing_threads 判重命中，避免重复回信。
            try:
                _ensure_mail_inquiry_imports._spm.spare_mail_create_task({
                    "task_id": _gen_task_id(),
                    "thread_msg_id": mid,
                    "status": "REJECTED",
                    "internal_status": "REJECTED",
                    "external_status": "REJECTED",
                    "latest_step": f"R_FR02_MISSING_FIELDS:{','.join(missing)}",
                })
            except Exception as e:
                print(f"[mail-inquiry] persist rejected marker failed: {e}")
            continue

        # ── 创建去重：按工程师初始询价邮件的 message-id（同一封不重复建任务）。
        # 不再按 project_no 去重——同一项目可有多次采购，各自建独立任务并生成各自的 NEU 任务号。
        task_id = _gen_task_id()
        deadline = _inquiry_deadline(m, fields.get("urgent", "24h"))

        task = {
            "task_id": task_id,
            "thread_msg_id": mid,
            "from_email": str(m.get("from_email") or "").strip(),
            # 记录工程师询价邮件的原始收件/抄送人，供外部流(E/G)按需抄送
            "inquiry_to_json": json.dumps(m.get("to_email_list") or [], ensure_ascii=False),
            "inquiry_cc_json": json.dumps(m.get("cc_email_list") or [], ensure_ascii=False),
            "inquiry_body": body[:4000],
            "project_no": fields.get("project_no", ""),
            "project_name": fields.get("project_name", ""),
            "part_type": fields.get("part_type", ""),
            "brand": fields.get("brand", ""),
            "pn": fields.get("pn", ""),
            "spec": fields.get("spec", ""),
            "condition": fields.get("condition", ""),
            "count": fields.get("count", ""),
            "address": fields.get("address", ""),
            "urgent": fields.get("urgent", "24h"),
            "latest_ship_time": fields.get("latest_ship_time", ""),
            "inquiry_deadline": deadline,
            "suppliers_json": "[]",
            "quotes_json": "[]",
            "internal_status": "R_INIT",
            "external_status": "R_SEND",
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
    # 项目名称（不跨行：值中只允许空格/Tab，不允许换行吞并下一字段）
    m = re.search(r"(?:项目名称?\s*[:：]?\s*)([\u4e00-\u9fff\w\-（）() \t]{2,40})", merged)
    if m and "project_name" not in out: out["project_name"] = m.group(1).strip()
    # 品牌（中英文均可：兼容 三星 / Seagate）
    m = re.search(r"品牌\s*[:：]?\s*([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9\-]{1,20})", merged)
    if m: out["brand"] = m.group(1)
    # PN（兼容 "PN：" 与 "型号（PN）："）
    m = re.search(r"(?:PN(?:\s*料号)?\s*[:：]?|型号（PN）\s*[:：])\s*([A-Za-z0-9\-/.]+)", merged, re.I)
    if m: out["pn"] = m.group(1)
    # 备件类型（兼容 "备件类型：" / "类型：" 开头，值为任意词）
    m = re.search(r"(?:备件类型\s*[:：]?\s*|类型\s*[:：]?\s*)([^\n：:]{1,20})", merged)
    if m: out["part_type"] = m.group(1).strip()
    # 成色（取值，不含 "成色：" 前缀）
    m = re.search(r"成色\s*[:：]?\s*(全新|原厂翻新|拆机二手)", merged)
    if m: out["condition"] = m.group(1)
    # 数量
    m = re.search(r"(?:采购数量|数量)\s*[:：]?\s*(\d+)", merged)
    if m: out["count"] = m.group(1)
    # 紧急程度（决定报价截止）：如 紧急程度：5min / 1h / 24小时 / 3天
    m = re.search(r"紧急程度\s*[:：]?\s*([\d]+\s*(?:分钟?|min|m|小时?|h|天|d))", merged, re.I)
    if m:
        out["urgent"] = m.group(1).strip()
    elif not (out.get("urgent") or ""):
        # 兜底：兼容旧式"询价时限/询价时间/回复时限"
        m = re.search(r"(?:(?:询价)?(?:回复)?(?:时限|时间|内))\s*[:：]?\s*([\d]+\s*(?:分钟?|min|m|小时?|h|天|d))", merged, re.I)
        if m:
            out["urgent"] = m.group(1).strip()
    # 最晚发货时间
    m = re.search(r"(?:最晚发货(?:时间)?\s*[:：]?\s*)(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)", merged)
    if m: out["latest_ship_time"] = m.group(1).replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
    # 规格：先匹配显式"规格:"字段，再从品牌/型号/描述里推断（如 "4TB 企业级硬盘" / "DDR4 3200MHz 16GB"）
    m = re.search(r"规格(?:参数)?\s*[:：]?\s*([^\n：:]{1,80})", merged)
    if m:
        out["spec"] = m.group(1).strip()
    elif not (out.get("spec") or ""):
        # 从 subject + 品牌描述里提取容量/频率/尺寸等规格关键词
        spec_keywords = re.findall(r"(\d+\s*(?:TB|GB|MB|MHz|GHz|U|寸|inch|英寸))", subject + merged, re.I)
        type_kw = re.search(r"(企业级|台式机|服务器|笔记本|SAS|SATA|NVMe|PCIe|固态硬盘|机械硬盘|内存|显卡|电源|主板)", subject + merged)
        pieces = []
        if spec_keywords:
            pieces.extend(spec_keywords[:2])
        if type_kw:
            pieces.append(type_kw.group(1))
        if pieces:
            out["spec"] = " ".join(pieces)
    # 规格兜底：至少把型号 PN 带上（PN 本身可作为规格参考）
    if not (out.get("spec") or "") and out.get("pn"):
        out["spec"] = out["pn"]
    # 收货地址
    m = re.search(r"(?:收货地址|收货地址(?:详情)?|地址)\s*[:：︓]?\s*([^\n]{3,80})", merged)
    if m: out["address"] = m.group(1).strip()
    # 联系人
    m = re.search(r"(?:收货人|联系人|收货联系人)\s*[:：]?\s*([\u4e00-\u9fff\w]{2,10})", merged)
    if m: out["receiver_name"] = m.group(1).strip()
    # 联系电话
    m = re.search(r"(?:联系电话|收货人电话|电话)\s*[:：]?\s*([\d\-+]{7,20})", merged)
    if m: out["receiver_phone"] = m.group(1).strip()
    return out


# ── mail-inquiry 字段 LLM 兜底（正则为主，仅关键字段缺失时调用）──
# 必填校验范围：除 latest_ship_time 外的全部关键字段都算必填（缺任一即回信拦截/LLM 补抽）
_MI_LLM_REQUIRED = ("project_no", "project_name", "part_type", "brand", "pn",
                    "spec", "condition", "count", "address", "urgent")

def _extract_needs_llm(fields: dict) -> bool:
    """正则结果是否缺关键字段 → 本轮需走 LLM 兜底。"""
    return any(not (fields.get(k) or "").strip() for k in _MI_LLM_REQUIRED)


def _llm_fallback_extract(body: str, subject: str, regex_fields: dict) -> dict:
    """用 DeepSeek 从询价邮件补抽缺失字段（仅当正则缺失关键字段时调用）。

    返回字段与 _extract_inquiry_fields 对齐：project_no/project_name/part_type/
    brand/pn/spec/condition/count/address/receiver_name/receiver_phone/
    inquiry_dur/latest_ship_time。LLM 失败时原样返回 regex_fields，保证不比正则差。
    """
    def _merge(result: dict) -> dict:
        merged = dict(regex_fields)
        for k, v in (result or {}).items():
            if k in merged and v not in (None, ""):
                merged[k] = v
        return merged

    try:
        from app.agent_chat import _load_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    except Exception:
        return regex_fields
    key = _load_deepseek_key()
    if not key:
        return regex_fields

    prompt = (
        "你是专业的备件采购询价邮件解析助手。请从工程师发起的【询价申请邮件】正文和主题中，"
        "抽取结构化字段，输出严格的 JSON（不要多余文字、不要代码块标记）。\n"
        "字段说明：\n"
        "- project_no 项目编号（如 PRJ-2026-0888，没写则空字符串）\n"
        "- project_name 项目名称（没写则空字符串，不要把主题里的占位符 XXX 当真实值）\n"
        "- part_type 备件类型（如 内存条/硬盘/主板；原文写 类型：X 则取 X）\n"
        "- brand 品牌（如 三星/Kingston）\n"
        "- pn 型号/PN 料号\n"
        "- spec 规格参数\n"
        "- condition 成色（全新/原厂翻新/拆机二手）\n"
        "- count 采购数量（数字字符串）\n"
        "- address 收货地址\n"
        "- receiver_name 收货联系人\n"
        "- receiver_phone 联系电话\n"
        "- inquiry_dur 询价回复时限（如 48h/24h/12h/1h）\n"
        "- latest_ship_time 最晚发货时间（统一格式 YYYY-MM-DD）\n"
        "规范：只把邮件里真实出现的信息填进去，未出现一律给空字符串，绝不编造。"
    )
    user_msg = f"【主题】\n{subject}\n\n【邮件正文】\n{body}\n\n【应输出 JSON 字段】\n"
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    try:
        import httpx as _httpx
        with _httpx.Client(timeout=60) as client:
            r = client.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                            headers={"Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json"},
                            json=payload)
            if r.status_code != 200:
                return regex_fields
            data = r.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        result = json.loads(content)
        if not isinstance(result, dict):
            return regex_fields
        return _merge(result)
    except Exception:
        return regex_fields


# ── 必填字段中文名（用于异常回信）──
_MI_FIELD_LABELS = {
    "part_type": "备件类型", "brand": "品牌", "pn": "PN/型号",
    "count": "数量", "spec": "规格", "condition": "成色",
    "project_no": "项目编号", "project_name": "项目名称",
    "address": "收货地址", "inquiry_dur": "询价时限", "latest_ship_time": "最晚发货时间",
}

def _reply_missing_fields(mail: dict, missing: list, fields: dict):
    """R-FR-02：向工程师回信指出缺失的必填字段，并提示补齐后重新发送。

    不创建任务、不进入询价流程。缺失字段由 missing(list) 给出。
    """
    try:
        from_email = str(mail.get("from_email") or "").strip()
        if not from_email:
            return
        reply_mid = _norm_mid(mail.get("message_id", ""))
        labels = [_MI_FIELD_LABELS.get(k, k) for k in missing]
        subject = "【询价申请】信息不完整，请补充后重新发送（请勿回复本邮件）"
        body = (
            "您好，已收到您的备件询价申请，但以下必填信息缺失，本次未进入询价流程。\n\n"
            "缺少字段：\n"
            + "\n".join(f"  - {lb}" for lb in labels)
            + "\n\n请补充上述字段后，【重新发送】一封完整的询价申请邮件。"
            "\n\n❗请勿回复本邮件：直接回复本邮件不会被系统识别。"
            "请【新写一封】询价申请邮件发送到本邮箱即可（不必保留本项目邮件）。"
            "\n\n（提示：请尽量包含 备件类型/品牌/PN型号/规格/成色/数量/收货地址/询价时限/最晚发货时间）"
            "\n\n- NeuOps 备件邮件询价系统"
        )
        tool_send_mail(to=[from_email], subject=subject, body_text=body,
                       reply_to_mail_id=reply_mid or None)
    except Exception as e:
        print(f"[mail-inquiry] reply_missing_fields failed: {e}")


def _step_sending_b(task: dict, cfg: dict, tpls: dict):
    """SENDING_B：渲染模板 B（不带收货地址）→ tool_batch_send_mail → 存 suppliers_json → WAITING_QUOTES。"""
    tid = task["task_id"]
    tpl_b = (tpls or {}).get("B", {}) or {}

    # 供应商池：只读配置（DB spare_mail_config.proc_participants 优先，skill JSON 兜底）
    suppliers = []
    for s in (cfg or {}).get("default_suppliers", []) or []:
        if isinstance(s, dict):
            name = str(s.get("name") or "").strip()
            email = str(s.get("email") or "").strip()
        else:
            name, email = str(s).strip(), ""
        if name and email:
            suppliers.append({"name": name, "email": email})

    # 渲染模板 B（每个供应商各渲染一份，supplier 字段不同）
    deadline_str = task.get("inquiry_deadline") or ""
    emails = [s["email"] for s in suppliers]
    urgent = task.get("urgent") or "24h"
    subject = (tpl_b.get("subject") or "").format(
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        count=task.get("count", ""),
        urgent=urgent,
        inquiry_dur=urgent,
        task_no=_task_neu_no(task),
    )
    body_fmt = tpl_b.get("body") or ""
    # 注意：B 询价对外不暴露内部项目编号/项目名称（供应商不该看到），一律置空
    ship_time = (task.get("latest_ship_time") or "").strip() or "尽快发货"  # 首封未写则按设计用"尽快发货"
    body_args = dict(
        project_no="",
        project_name="",
        part_type=task.get("part_type", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        spec=task.get("spec", ""),
        condition=task.get("condition", ""),
        count=task.get("count", ""),
        latest_ship_time=ship_time,
        urgent=urgent,
        inquiry_dur=urgent,
        deadline=deadline_str,
        task_no=_task_neu_no(task),
        supplier="{supplier}",
    )
    # 渲染模板 B（每个供应商各渲染一份，supplier 字段不同）
    rendered_body = body_fmt.format(**body_args).replace("{supplier}", "供应商您好")
    # B 询价函也要带上"采购发起人（工程师）+ 首封邮件 to/cc + 系统全局抄送"（对外询价不暴露审批人）
    def _sp_cc():
        out, seen = [], set()
        for e in (_fetch_global_cc_list() or []):
            e = str(e or "").strip()
            if e and "@" in e and e not in seen:
                seen.add(e); out.append(e)
        eng = str(task.get("from_email") or "").strip()
        try:
            ito = json.loads(task.get("inquiry_to_json") or "[]")
            icc = json.loads(task.get("inquiry_cc_json") or "[]")
        except Exception:
            ito, icc = [], []
        for e in ([eng] if (eng and "@" in eng) else []) + list(ito) + list(icc):
            e = str(e or "").strip()
            if e and "@" in e and e not in seen:
                seen.add(e); out.append(e)
        self_e = str((cfg or {}).get("proc_mail_username") or "").strip().lower()
        return [e for e in out if not (self_e and e.lower() == self_e)]
    b_cc = _sp_cc()
    batch_r = tool_batch_send_mail(receiver_email_list=emails, subject=subject, body_text=rendered_body, cc=b_cc)
    # 全程归档：B 询价函（每封供应商各一条，携带 msg_id/收件人/抄送）
    for ok_m in batch_r.get("sent", []):
        _archive_sent_mail(tid, "B", {
            "success": True, "message_id": ok_m.get("message_id", "") or "",
            "subject": subject, "to": [ok_m.get("email", "")], "cc": b_cc or [],
        })

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

    # 存库并转到外部流 R_WAIT_QUOTES（同时保留 status 兼容）
    spm = _ensure_mail_inquiry_imports._spm
    spm.spare_mail_update_task(tid, {
        "suppliers_json": json.dumps(suppliers_out, ensure_ascii=False),
        "external_status": "R_WAIT_QUOTES",
        "status": "WAITING_QUOTES",
        "latest_step": f"R_SEND→R_WAIT_QUOTES(sent={sum(1 for x in suppliers_out if x['sent_ok'])}/{len(suppliers_out)})",
    })
    return True


def _quote_key_missing(parsed: dict) -> bool:
    """报价关键字段是否缺失：单价/成色/数量/发货周期 任一为空则认为需要 LLM 兜底补齐。"""
    for k in ("unit_price", "condition", "count", "ship_time"):
        v = parsed.get(k)
        if v in (None, "", 0):
            return True
    return False


def _llm_parse_quote_fallback(body: str, regex_result: dict) -> dict:
    """报价解析的 LLM 兜底：当正则结果任一关键字段缺失时，用 DeepSeek 补抽。

    返回 unit_price/condition/count/ship_time。LLM 失败时原样返回 regex_result，保证不比正则差。
    """
    # 全部关键字段都已规则解析出则无需 LLM
    if not _quote_key_missing(regex_result):
        return regex_result
    try:
        from app.agent_chat import _load_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    except Exception:
        return regex_result
    key = _load_deepseek_key()
    if not key:
        return regex_result
    prompt = (
        "你是专业的供应商报价邮件解析助手。请从【供应商报价邮件】正文中抽取报价字段，"
        "输出严格的 JSON（不要多余文字、不要代码块标记）。\n"
        "字段说明：\n"
        "- unit_price 单价（数字，如 1280 或 1280.5；若报价为范围取较低值；不出现则空）\n"
        "- condition 成色（全新/原厂翻新/拆机二手，没有则空）\n"
        "- count 采购数量（数字字符串，没有则空）\n"
        "- ship_time 交货/发货周期（如 3个工作日，没有则空）\n"
        "规范：只把邮件里真实出现的信息填进去，未出现一律空字符串，绝不编造。"
    )
    user_msg = f"【邮件正文】\n{body}\n\n【应输出 JSON】\n"
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.05,
        "max_tokens": 400, "response_format": {"type": "json_object"},
    }
    try:
        import httpx as _httpx
        with _httpx.Client(timeout=60) as client:
            r = client.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                            headers={"Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json"},
                            json=payload)
            if r.status_code != 200:
                return regex_result
            data = r.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        result = json.loads(content)
        if not isinstance(result, dict):
            return regex_result
        merged = dict(regex_result)
        for k, v in result.items():
            if v not in (None, "") and k in merged:
                merged[k] = v
        return merged
    except Exception:
        return regex_result


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
            "external_status": "R_DECIDING",
            "status": "DECIDING_LOWEST",
            "latest_step": "R_WAIT_QUOTES→R_DECIDING(no_sent_suppliers)",
        })
        return True

    # 拉收件箱：用 match_in_reply_to_msg_ids 精确匹配线程
    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60 * 2
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = _tick_cached_read_inbox(since_timestamp=since_ts, exclude_sender_email_list=exclude,
                             match_in_reply_to_msg_ids=match_ids)

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

            # 解析报价正文：单价/成色/数量/发货时间（正则为主，任一关键字段缺失时 LLM 兜底补齐）
            body = m.get("mail_body_text") or ""
            parsed = _parse_quote_body(body)
            if _quote_key_missing(parsed):
                print(f"[mail-inquiry] 报价关键字段缺失({from_email})，LLM 兜底补齐")
                parsed = _llm_parse_quote_fallback(body, parsed)
            has_unit = parsed.get("unit_price") not in (None, "", 0)
            parse_failed = not has_unit

            # 迟到判断
            deadline_str = task.get("inquiry_deadline", "")
            try:
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
                "refs": (m.get("references") or "").strip(),
                "is_late": is_late,
                "parse_failed": parse_failed,
                "raw_subject": m.get("subject", ""),
                "reply_all": {
                    "from_email": m.get("from_email", ""),
                    "to_email_list": m.get("to_email_list") or [],
                    "cc_email_list": m.get("cc_email_list") or [],
                },
                "raw_body": body[:800],
            })
            existing_msg_ids.add(mid)

    # 判断是否到点/全部已回
    all_replied = all(
        not s.get("sent_ok")
        or any(str(q.get("email") or "").lower() == str(s.get("email") or "").lower()
               for q in quotes)
        for s in suppliers
    )
    deadline_str = task.get("inquiry_deadline", "")
    try:
        deadline_ts = int(datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S").timestamp()) if deadline_str else 0
    except Exception:
        deadline_ts = 0
    now_ts = int(time.time())

    if all_replied or (deadline_ts and now_ts >= deadline_ts):
        _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
            "quotes_json": json.dumps(quotes, ensure_ascii=False),
            "external_status": "R_DECIDING",
            "status": "DECIDING_LOWEST",
            "latest_step": f"R_WAIT_QUOTES→R_DECIDING(all_replied={all_replied}, deadline_hit={bool(deadline_ts and now_ts >= deadline_ts)})",
        })
        return True

    # 还没到点/未全部回：更新 quotes_json 后继续等
    _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
        "quotes_json": json.dumps(quotes, ensure_ascii=False),
        "latest_step": f"WAITING_QUOTES({len(quotes)} quotes so far)",
    })
    return False


def _parse_quote_table(body: str) -> dict:
    """解析"报价表格"并定位单价/数量/货期/成色列。

    覆盖三种常见的富文本表格表示（取决于发件客户端如何渲染）：
    1) 列用制表符分隔（Excel/富文本直接粘贴）：
        序 日期 品牌 数量 单价 总价 货期 成色
        1  2025年8月31日  Seagate  3 1000 3000 7天 全新
    2) 列用多个空格分隔（纯文本对齐）。
    3) 163 富文本转换为 "| 单元格 | 单元格 |" 的伪竖线表格（行首可能带表头文字 / 行尾缺 |）。
    识别含"单价/数量/货期"的表头行定位列号，再从序号为数字的数据行读取对应列。
    解析不出时返回 {}。
    """
    out = {}
    lines = [ln.rstrip().strip() for ln in str(body or "").splitlines()]
    header_cells = None
    header_idx = None

    # 候选分隔符：若行内出现竖线用 |，否则依次用 Tab / ≥2空格
    def _split(ln):
        for delim in (r"\|", r"\t", r" {2,}"):
            c = [x.strip() for x in re.split(delim, ln) if x.strip()]
            if len(c) >= 3:
                return c
        return [ln]

    # 找表头行：切成列后同时含"单价"类 与 至少一个辅助列词
    for i, ln in enumerate(lines):
        if not ln:
            continue
        cells = _split(ln)
        if len(cells) < 3:
            continue
        has_price = any(("单价" in c or "价格" in c or "报价" in c) for c in cells)
        has_aux = any(("数量" in c or "总价" in c or "货期" in c or "成色" in c or "型号" in c or "日期" in c or "序" in c or "备注" in c) for c in cells)
        if has_price and has_aux:
            header_cells, header_idx = cells, i
            break
    if not header_cells:
        return out

    def _find(keys):
        for j, c in enumerate(header_cells):
            if any(k in c for k in keys):
                return j
        return None
    j_price = _find(("单价", "单位价格"))
    j_count = _find(("数量", "交付数量"))
    j_lead = _find(("货期", "交货周期", "周期", "交货"))
    j_cond = _find(("成色", "新旧"))

    for ln in lines[header_idx + 1:]:
        if not ln:
            continue
        cells = _split(ln)
        if not cells:
            continue
        # 数据行首列应为序号数字
        if not re.match(r"^\d+", cells[0]):
            continue
        # 列数一致性：表头 H 列、数据行若被拆成显著不同列数（如 163 把型号/品牌拆多格），
        # 按索引取值必然错位（把总价当单价）。宁可解析失败走 LLM 兜底，也不给错值。
        if abs(len(cells) - len(header_cells)) > 1:
            continue
        if j_price is not None and j_price < len(cells) and out.get("unit_price") is None:
            pm = re.search(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", cells[j_price])
            if pm:
                out["unit_price"] = float(pm.group(0).replace(",", ""))
        if j_count is not None and j_count < len(cells) and "count" not in out:
            qm = re.search(r"\d+", cells[j_count])
            if qm:
                out["count"] = int(qm.group(0))
        if j_lead is not None and j_lead < len(cells) and "ship_time" not in out:
            lm = re.search(r"[\d\u4e00-\u9fff]+", cells[j_lead].replace(",", ""))
            if lm:
                out["ship_time"] = lm.group(0).strip()
        if j_cond is not None and j_cond < len(cells) and "condition" not in out:
            cm = re.search(r"全新|原厂翻新|拆机二手|二手|全新原装", cells[j_cond])
            if cm:
                out["condition"] = cm.group(0)
        if out.get("unit_price") is not None:
            break
    return out


def _parse_quote_body(body: str) -> dict:
    """从供应商报价正文抽单价/成色/数量/发货时间（正则，失败留空）。

    同时支持普通文本字段、Markdown 表格（| 表头 | 行数据 |）、以及用户模板型的
    "制表符/多空格分隔"报价表格三种常见报价格式。
    先剥离"回复引用旧询价"的内容（> 前缀行 / '在 ... 中写道' 之后），
    确保解析只看供应商自己新写的报价，避免被原询价里的 单价/数量 干扰。
    """
    out = {}

    # ── 剥离被引用的旧询价（邮件流"全部回复"携带的原文）──
    body = str(body or "")
    # 1) 截断到"在 ... 中写道："引用标记之前
    m_cut = re.search(r"在\s*.{0,60}写道[:：]?", body)
    if m_cut:
        body = body[:m_cut.start()]
    # 2) 去掉以 > 开头的引用行
    body_lines = [ln for ln in body.splitlines() if not ln.strip().startswith(">")]
    body = "\n".join(body_lines)

    # ── 表格格式：优先尝试解析 | A | B | ... | 表格行 ──
    # 找包含至少 单价/价格 且 数量/货期/成色 之一的“数据行”
    table_rows = re.findall(r"^\s*\|([^\n]+)\|\s*$", body, re.M)
    numeric_rows = []
    for row in table_rows:
        cells = [c.strip() for c in row.split("|")]
        cells = [c for c in cells if c]  # 去掉空单元格
        # 数据行至少包含一个数字（数字行/单价/数量）
        if any(re.search(r"\d", c) for c in cells) and any(c for c in cells):
            numeric_rows.append(cells)
    # 表头识别：表头行含 单价|价格 等关键词
    header_row = None
    for row in table_rows:
        cells = [c.strip() for c in row.split("|")]
        cells = [c for c in cells if c]
        if any(("单价" in c or "价格" in c or "报价" in c) for c in cells):
            header_row = cells
            break
    # 用表头定位 数量/货期/成色 列
    idx_price = idx_qty = idx_lead = idx_cond = None
    if header_row:
        def _find(cands):
            for i, c in enumerate(header_row):
                if any(k in c for k in cands):
                    return i
            return None
        idx_price = _find(("单价", "价格", "报价"))
        idx_qty = _find(("数量", "交付数量"))
        idx_lead = _find(("货期", "交货", "周期", "发货"))
        idx_cond = _find(("成色", "新旧"))
    if header_row and numeric_rows:
        # 列对齐校验：任一数据行与表头列数差异过大 → 163 拆格错位，整表不可靠，不切列（走后续兜底）
        _hcols = len(header_row)
        _misaligned = any(abs(len(nr) - _hcols) > 1 for nr in numeric_rows)
        if not _misaligned:
            for cells in numeric_rows:
                if idx_price is not None and idx_price < len(cells):
                    pm = re.search(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", cells[idx_price])
                    if pm and out.get("unit_price") is None:
                        out["unit_price"] = float(pm.group(0).replace(",", ""))
                if idx_qty is not None and idx_qty < len(cells) and "count" not in out:
                    qm = re.search(r"\d+", cells[idx_qty])
                    if qm: out["count"] = int(qm.group(0))
                if idx_lead is not None and idx_lead < len(cells) and "ship_time" not in out:
                    lm = re.search(r"[\d\u4e00-\u9fff]+", cells[idx_lead].replace(",", ""))
                    if lm: out["ship_time"] = lm.group(0).strip()
                if idx_cond is not None and idx_cond < len(cells) and "condition" not in out:
                    cm = re.search(r"全新|原厂翻新|拆机二手|二手|全新原装", cells[idx_cond])
                    if cm: out["condition"] = cm.group(0)

    # ── 普通文本格式（表格未解出时兜底）──
    # 先尝试"制表符/多空格分隔"的报价表格（用户模板型），再退到键值正则
    if out.get("unit_price") is None:
        _tbl = _parse_quote_table(body)
        for _k, _v in _tbl.items():
            if _v not in (None, "") and out.get(_k) in (None, ""):
                out[_k] = _v
    if out.get("unit_price") is None:
        # 支持千分位：￥1,280 / 1,280.00 / 1280
        m = re.search(r"(?:单价|报价|含税价|价格)\s*[:：]?\s*[¥￥$]?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)", body)
        if m: out["unit_price"] = float(m.group(1).replace(",", ""))
    if "condition" not in out:
        m = re.search(r"(?:成色|新旧)\s*[:：]?\s*(全新|原厂翻新|拆机二手|二手|全新原装)", body)
        if m: out["condition"] = m.group(1)
    if "count" not in out:
        m = re.search(r"(?:数量|订货量)\s*[:：]?\s*(\d+)", body)
        if m: out["count"] = int(m.group(1))
    if "ship_time" not in out:
        m = re.search(r"(?:发货(?:时间|周期)?|交货(?:时间|周期)?|货期|交期|到货)\s*[:：]?\s*(?:约)?([\d\u4e00-\u9fff\s]{1,12}?(?:天|日|周|小时内?|工作日))|\d{4}[-/]\d{1,2}[-/]\d{1,2}", body)
        if m: out["ship_time"] = m.group(1).strip() if m.group(1) else m.group(0).strip()
    return out


def _step_deciding_lowest(task: dict, cfg: dict, tpls: dict):
    """外部流 R_DECIDING：算最低价 + 将未选中供应商标记截止 → 设 external_status=R_ORDER；
    内部流随后（R_INIT）才会发送模板 D 审批汇总。

    无有效报价时区分两种情况：
    - quotes 为空（根本没有供应商回复）→ 模板 F 中止（ABORT_NO_QUOTE），双流终态。
    - 收到报价但单价解析失败（parse_failed）→ 不解散，向对应供应商发澄清邮件让其补正，
      任务回退 R_WAIT_QUOTES 继续等，避免误中止已报价的供应商。
    """
    tid = task["task_id"]
    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    tpl_f = (tpls or {}).get("F", {}) or {}
    spm = _ensure_mail_inquiry_imports._spm

    # 过滤有效报价（不是迟到、单价可解析）
    valid = [q for q in quotes if not q.get("is_late") and q.get("unit_price") not in ("", None)]

    if not valid:
        # 收到报价但解析失败（parse_failed 且未迟到）：发澄清回退继续等，不中止
        # 已澄清过（clarify_sent=True）仍解析失败 → 视为确实无法得到有效报价，转入中止
        bad = [q for q in quotes if q.get("parse_failed") and not q.get("is_late")]
        already_clarified = [q for q in bad if q.get("clarify_sent")]
        if bad and not already_clarified:
            for q in bad:
                email = (q.get("email") or "").strip()
                reply_mid = _norm_mid(q.get("msg_id", ""))
                if not email:
                    continue
                subj_clar = (f"【询价补充】补正报价信息 - 任务 {tid}")
                body_clar = (
                    "您好，我们已收到贵司对本次备件询价的报价邮件，但未能从中识别到明确的【含税单价】，"
                    "无法纳入比价。\n\n"
                    "请回复本邮件补充以下信息（缺一项补一项即可）：\n"
                    "  - 含税单价（例如：￥1,280）\n"
                    "  - 成色（全新 / 原厂翻新 / 拆机二手）\n"
                    "  - 可发货数量\n"
                    "  - 交货周期（例如：3 个工作日）\n\n"
                    "请直接在一条回复里说明，谢谢！\n"
                    "（说明：如果误发，可忽略本邮件。）\n\n- NeuOps 备件邮件询价系统"
                )
                tool_send_mail(to=[email], subject=subj_clar, body_text=body_clar,
                               reply_to_mail_id=reply_mid or None)
                q["clarify_sent"] = True
                print(f"[mail-inquiry] 报价解析失败，向 {email} 发澄清邮件")
            # 回退 R_WAIT_QUOTES，继续等待供应商补正，不推进 D/汇总，也不 ABORT
            spm.spare_mail_update_task(tid, {
                "quotes_json": json.dumps(quotes, ensure_ascii=False),
                "external_status": "R_WAIT_QUOTES",
                "status": "WAITING_QUOTES",
                "latest_step": "R_DECIDING→R_WAIT_QUOTES(parse_failed, clarification sent)",
            })
            return True

        # 完全没收到任何报价 → 中止：模板 F，回复模板 A 会话（工程师询价线程）
        reason = "无有效报价（全部迟到或供应商未回复）" if quotes else "无供应商回复"
        fmt_args = dict(
            project_no=task.get("project_no", ""),
            project_name=task.get("project_name", ""),
            part_type=task.get("part_type", ""),
            brand=task.get("brand", ""),
            pn=task.get("pn", ""),
            stop_reason=reason,
            task_no=_task_neu_no(task),
        )
        body = _safe_format(tpl_f.get("body") or "", fmt_args)
        subj = _safe_format(tpl_f.get("subject") or "", fmt_args)
        # 回复工程师询价线程，末尾引用原始采购申请原文
        tool_send_mail(to=[str(cfg.get("proc_mail_username") or "").strip()],
                       subject=subj, body_text=body + _quote_orig_body(task.get("inquiry_body")),
                       reply_to_mail_id=task.get("thread_msg_id") or None)
        spm.spare_mail_update_task(tid, {
            "status": "DONE", "external_status": "R_ABORT", "internal_status": "R_CLOSED",
            "latest_step": "R_DECIDING→R_ABORT(ABORT_NO_QUOTE)",
            "lowest_supplier": "", "lowest_quote": "",
        })
        return True

    # 最低价
    valid.sort(key=lambda q: float(q.get("unit_price") or 1e18))
    lowest = valid[0]
    lowest_quote_str = f"¥{lowest.get('unit_price','')}"
    lowest_supplier = lowest.get("supplier", "")

    # 未选中供应商标记截止（回复报价后即停在三方询价期）
    suppliers_json = _safe_json_loads(task.get("suppliers_json") or "[]")
    chosen_emails = {str(q.get("email") or "").lower() for q in valid if q.get("email")}
    for s in suppliers_json:
        if s.get("sent_ok") and (str(s.get("email") or "").lower() not in chosen_emails):
            s["closed"] = True
            s["closed_reason"] = "本轮询价未被选中"

    spm.spare_mail_update_task(tid, {
        "lowest_supplier": lowest_supplier,
        "lowest_quote": json.dumps(lowest, ensure_ascii=False),
        "suppliers_json": json.dumps(suppliers_json, ensure_ascii=False),
        "external_status": "R_ORDER",
        "status": "DECIDING_LOWEST",
        "latest_step": f"R_DECIDING→R_ORDER(lowest={lowest_supplier}@{lowest_quote_str})",
    })
    return True


def _step_ordering(task: dict, cfg: dict, tpls: dict):
    """外部流 R_ORDER：定位选中供应商报价 Message-ID → 渲染模板 E（回复该报价会话、带收货地址）→ R_WAIT_SHIPPING。
    未确认 target（等内部审批）则跳过，不做任何状态迁移。
    """
    tid = task["task_id"]
    tpl_e = (tpls or {}).get("E", {}) or {}
    target = task.get("target_supplier", "")
    if not target:
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

    latest_ship_time = (task.get("latest_ship_time") or "").strip() or "尽快发货"  # 首封未写最晚发货时间 → 尽快发货
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
        task_no=_task_neu_no(task),
    )
    subj = (tpl_e.get("subject") or "").format(
        project_no=task.get("project_no", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        count=task.get("count", ""),
        task_no=_task_neu_no(task),
    )

    # 在选中供应商报价邮件线程上回复——构造完整 References 链确保 RFC 会话链不中断
    # C 报价邮件自带的 References（可能含 B/A 链）作为 E 的上游链
    c_refs = (target_quote or {}).get("refs", "") or ""
    c_cc = ((target_quote or {}).get("reply_all") or {}).get("cc_email_list") or []
    body_full = body + _quote_orig_body((target_quote or {}).get("raw_body"))
    # 外部流 E：发选中供应商；抄送=审批人+全局抄送+工程师+询价收/抄送+供应商报价抄送
    e_cc = _external_flow_cc(task, cfg, exclude_to=(target_email,), extra_cc=c_cc)
    e_args = dict(
        to=[target_email] if target_email else [str(cfg.get("proc_mail_username") or "").strip()],
        subject=subj, body_text=body_full, cc=e_cc or None,
        reply_to_mail_id=reply_mid or None,
        reply_refs_chain=c_refs or None,
    )
    mail_r = tool_send_mail(**e_args)
    e_mail_msg_id = (mail_r or {}).get("message_id") or ""
    _archive_sent_mail(tid, "E", mail_r)
    # 落库 E 的完整 References 链（DB 优先，G 不再现取邮箱）
    e_built_refs = ((c_refs or "") + " " + (reply_mid or "")).strip() if c_refs else (reply_mid or "")
    _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
        "external_status": "R_WAIT_SHIPPING",
        "status": "ORDERING",
        "e_mail_msg_id": e_mail_msg_id,
        "e_refs_chain": e_built_refs,
        "latest_step": f"R_ORDER→R_WAIT_SHIPPING(sent_to={target_email}, e_msg_id={e_mail_msg_id})",
    })
    return True


# ════════════════════════════════════════════════════════════════
# 双邮件流 step 调度（内部流 + 外部流）
# ════════════════════════════════════════════════════════════════

def _mi_step_internal(task: dict, cfg: dict, tpls: dict) -> bool:
    """内部流：按 internal_status 推进。返回 True 表示该任务发生了状态迁移。"""
    st = task.get("internal_status") or "R_INIT"
    if st == "R_INIT":
        return _mi_internal_send_d(task, cfg, tpls)
    if st == "R_APPROVAL":
        return _mi_internal_wait_approval(task, cfg, tpls)
    return False


def _mi_internal_send_d(task: dict, cfg: dict, tpls: dict) -> bool:
    """内部流 R_INIT：报价就绪（外部流已定最低价）后发送模板 D 汇总邮件
    （回复工程师询价线程 + 抄送审批人）→ 设 internal_status=R_APPROVAL。
    幂等：已发过 D（d_mail_msg_id 非空）则仅确保状态，不重复发送。
    """
    tid = task["task_id"]
    lowest_supplier = task.get("lowest_supplier") or ""
    if not lowest_supplier:
        return False  # 报价未就绪，等外部流 R_DECIDING

    spm = _ensure_mail_inquiry_imports._spm
    # 幂等：若已进入 R_APPROVAL 且已发 D，直接返回
    if task.get("internal_status") == "R_APPROVAL":
        return False
    if task.get("d_mail_msg_id"):
        spm.spare_mail_update_task(tid, {"internal_status": "R_APPROVAL"})
        return False

    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    valid = [q for q in quotes if not q.get("is_late") and q.get("unit_price") not in ("", None)]
    valid.sort(key=lambda q: float(q.get("unit_price") or 1e18))
    lowest = valid[0] if valid else {}
    lowest_quote_str = f"¥{lowest.get('unit_price','')}"
    lowest_supplier = lowest.get("supplier", "") or lowest_supplier
    approvers = list((cfg or {}).get("approver_emails") or [])

    tpl_d = (tpls or {}).get("D", {}) or {}
    suppliers_str = "\n".join(
        f"  - {q.get('supplier','')} <{q.get('email','')}>：¥{q.get('unit_price','')} "
        f"{q.get('condition','')} x{q.get('count','')} / 发货 {q.get('ship_time','')}"
        for q in valid
    )
    body_d = _safe_format(tpl_d.get("body") or "", dict(
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
        task_no=_task_neu_no(task),
    ))
    subj_d = _safe_format(tpl_d.get("subject") or "", dict(
        project_no=task.get("project_no", ""),
        brand=task.get("brand", ""),
        pn=task.get("pn", ""),
        suppliers_count=len(valid),
        task_no=_task_neu_no(task),
    ))
    # 回复工程师询价线程 + 抄送审批人+系统抄送；正文末尾引用工程师原始采购申请原文（同一线程内带原文）
    body_d_full = body_d + _quote_orig_body(task.get("inquiry_body"))
    # 内部流收件人：工程师始终在收件人(To)里；抄送 = 审批人 + 全局系统抄送（不含供应商）
    engineer_email = (task.get("from_email") or "").strip()
    d_to = [engineer_email] if (engineer_email and "@" in engineer_email) \
        else [str(cfg.get("proc_mail_username") or "").strip()]
    d_cc = list(approvers) if approvers else []
    _sys_cc = _fetch_global_cc_list()
    for _cc in (_sys_cc or []):
        if _cc and _cc not in d_cc:
            d_cc.append(_cc)
    # 内部邮件包含工程师 + 工程师询价邮件所携带的抄送地址
    try:
        _inq_cc = json.loads(task.get("inquiry_cc_json") or "[]")
    except Exception:
        _inq_cc = []
    for _cc in _inq_cc:
        _cc = str(_cc).strip()
        if _cc and _cc not in d_cc and _cc != engineer_email:
            d_cc.append(_cc)
    d_sent = tool_send_mail(
        to=d_to,
        subject=subj_d, body_text=body_d_full,
        cc=d_cc or None,
        reply_to_mail_id=task.get("thread_msg_id") or None,
        reply_all_from={
            "from_email": task.get("from_email", ""),
            "to_email_list": [task.get("from_email", "")] if engineer_email else [],
            "cc_email_list": d_cc,
        },
    )
    d_msg_id = d_sent.get("message_id", "") if isinstance(d_sent, dict) else ""
    _archive_sent_mail(tid, "D", d_sent)

    spm.spare_mail_update_task(tid, {
        "d_mail_msg_id": d_msg_id,
        "approval_state": "pending",
        "approval_result": "",
        "lowest_supplier": lowest_supplier,
        "lowest_quote": json.dumps(lowest, ensure_ascii=False),
        "internal_status": "R_APPROVAL",
        "latest_step": f"R_INIT→R_APPROVAL(D_sent, lowest={lowest_supplier}@{lowest_quote_str})",
    })
    return True


def _valid_quotes_list(task: dict) -> list:
    """任务的有效报价（无迟到 + 单价可解析），已按单价升序。"""
    quotes = _safe_json_loads(task.get("quotes_json") or "[]")
    valid = [q for q in quotes if not q.get("is_late") and q.get("unit_price") not in ("", None)]
    valid.sort(key=lambda q: float(q.get("unit_price") or 1e18))
    return valid


def _mi_internal_wait_approval(task: dict, cfg: dict, tpls: dict) -> bool:
    """内部流 R_APPROVAL：在 D 线程里区分两类内部分支：
    - 审批人白名单回复：确认采购（最低价/指定供应商）走外部流订货；全部拒绝 → 模板 F 中止。
    - 非审批人（工程师）回复"备件更换完成"：向选中供应商线程发模板 G 结算邮件 → R_CLOSED/DONE。
    二者都可能在同一轮询中出现，需按发件人区分。
    """
    tid = task["task_id"]
    approvers = [str(e).lower().strip() for e in (cfg or {}).get("approver_emails") or [] if e]
    lowest_supplier = task.get("lowest_supplier", "")
    target = task.get("target_supplier", "")
    valid = _valid_quotes_list(task)
    tpl_f = (tpls or {}).get("F", {}) or {}
    tpl_g = (tpls or {}).get("G", {}) or {}
    spm = _ensure_mail_inquiry_imports._spm

    # 未配置审批人 → 自动采纳最低价，交给外部流订货（仍保持 R_APPROVAL 等工程师回执）
    if not approvers and not target and lowest_supplier:
        spm.spare_mail_update_task(tid, {
            "target_supplier": lowest_supplier,
            "approval_state": "auto_approved",
            "approval_result": "no_approver_configured",
            "latest_step": f"R_APPROVAL(auto_approved, target={lowest_supplier})",
        })
        return True

    # 匹配线程：同时匹配 D 邮件 message_id 与原始询价 thread_msg_id，
    # 以兼容审批人回 D 线程、工程师回原始询价线程两种消息来源。
    d_msg_id = _norm_mid(task.get("d_mail_msg_id", ""))
    thread_mid = _norm_mid(task.get("thread_msg_id", ""))
    match_ids = []
    if d_msg_id:
        match_ids.append(d_msg_id)
    if thread_mid and thread_mid != d_msg_id:
        match_ids.append(thread_mid)
    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60 * 2
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = _tick_cached_read_inbox(since_timestamp=since_ts, exclude_sender_email_list=exclude,
                             match_in_reply_to_msg_ids=match_ids)
    if not r.get("success"):
        return False

    changed = False
    for m in r.get("mails", []):
        from_email = str(m.get("from_email") or "").lower().strip()
        body = (m.get("mail_body_text") or "") + "\n" + (m.get("subject") or "")

        if from_email in approvers:
            # ── 审批人分支 ──
            if not target:
                if re.search(r"全部报价不可选|全部不可选|任务终止|终止询价|全部拒绝", body):
                    fmt_args = dict(
                        project_no=task.get("project_no", ""),
                        project_name=task.get("project_name", ""),
                        part_type=task.get("part_type", ""),
                        brand=task.get("brand", ""),
                        pn=task.get("pn", ""),
                        stop_reason="审批人全部拒绝：全部报价不可选",
                        task_no=_task_neu_no(task),
                    )
                    body_f = _safe_format(tpl_f.get("body") or "", fmt_args)
                    subj_f = _safe_format(tpl_f.get("subject") or "", fmt_args)
                    # 内部流收件人：工程师始终在收件人(To)里；抄送 = 审批人 + 全局系统抄送（不含供应商）
                    eng = (task.get("from_email") or "").strip()
                    f_to = [eng] if (eng and "@" in eng) \
                        else [str(cfg.get("proc_mail_username") or "").strip()]
                    f_cc = list(approvers) if approvers else []
                    for _c in (_fetch_global_cc_list() or []):
                        if _c and _c not in f_cc:
                            f_cc.append(_c)
                    # 内部邮件包含工程师 + 工程师询价邮件所携带的抄送地址
                    try:
                        _finq_cc = json.loads(task.get("inquiry_cc_json") or "[]")
                    except Exception:
                        _finq_cc = []
                    for _c in _finq_cc:
                        _c = str(_c).strip()
                        if _c and _c not in f_cc and _c != eng:
                            f_cc.append(_c)
                    # 回复工程师询价线程，末尾引用原始采购申请原文
                    f_sent = tool_send_mail(to=f_to, subject=subj_f,
                                            body_text=body_f + _quote_orig_body(task.get("inquiry_body")),
                                            cc=f_cc or None,
                                            reply_to_mail_id=task.get("thread_msg_id") or None)
                    _archive_sent_mail(tid, "F", f_sent)
                    spm.spare_mail_update_task(tid, {
                        "approval_state": "rejected",
                        "approval_result": "ALL_REJECTED",
                        "approver_email": from_email,
                        "internal_status": "R_CLOSED",
                        "external_status": "R_ABORT",
                        "status": "DONE",
                        "latest_step": "R_APPROVAL→R_CLOSED(ABORT_ALL_REJECTED)",
                    })
                    return True
                if re.search(r"确认采购|同意采购|批准采购|确认订货|批准订货|采购通过", body):
                    specified = ""
                    for q in valid:
                        sname = q.get("supplier", "")
                        if sname and sname in body:
                            specified = sname
                            break
                    target = specified or lowest_supplier
                    result_label = f"指定供应商:{target}" if specified else f"沿用最低价:{lowest_supplier}"
                    spm.spare_mail_update_task(tid, {
                        "target_supplier": target,
                        "approval_state": "approved",
                        "approval_result": result_label,
                        "approver_email": from_email,
                        "latest_step": f"R_APPROVAL(approved by {from_email}, {result_label})",
                    })
                    changed = True
        else:
            # ── 工程师回执分支（非审批人）：备件更换完成 → 发模板 G 结算 → R_CLOSED/DONE ──
            if re.search(r"备件更换完成|更换完成|到货更换完成", body):
                launch_target = (task.get("target_supplier") or lowest_supplier or "")
                target_email, reply_mid = "", ""
                target_quote_g = None
                for q in _safe_json_loads(task.get("quotes_json") or "[]"):
                    if q.get("supplier") == launch_target and q.get("email"):
                        target_email = q.get("email")
                        reply_mid = _norm_mid(q.get("msg_id", ""))
                        target_quote_g = q
                        break
                if target_email:
                    fmt_args = dict(
                        supplier=launch_target,
                        project_no=task.get("project_no", ""),
                        project_name=task.get("project_name", ""),
                        part_type=task.get("part_type", ""),
                        brand=task.get("brand", ""),
                        pn=task.get("pn", ""),
                        spec=task.get("spec", ""),
                        condition=task.get("condition", ""),
                        count=task.get("count", ""),
                        address=task.get("address", ""),
                        unit_price=(target_quote_g or {}).get("unit_price", ""),
                        ship_time=(target_quote_g or {}).get("ship_time", ""),
                        request_time=task.get("created_at", ""),
                        ship_no=task.get("shipped_no", ""),
                        arrive_time=task.get("latest_ship_time", ""),
                        task_no=_task_neu_no(task),
                    )
                    # 采购确认正文：仅"全量信息块"，不再用模板的【订货摘要】+签名
                    _smeta = {}
                    try:
                        _smeta = json.loads(task.get("shipped_mail_meta") or "{}")
                    except Exception:
                        _smeta = {}
                    _g_rows = [
                        ("项目号", task.get("project_no", "")),
                        ("项目名称", task.get("project_name", "")),
                        ("申请时间", task.get("created_at", "")),
                        ("备件", f"{task.get('part_type','')} / {task.get('brand','')} / {task.get('pn','')} {task.get('spec','')}"),
                        ("成色", task.get("condition", "")),
                        ("数量", str(task.get("count", ""))),
                        ("成交供应商", launch_target),
                        ("成交单价", f"¥{(target_quote_g or {}).get('unit_price','')}"),
                        ("成交货期", (target_quote_g or {}).get("ship_time", "")),
                        ("收货地址", task.get("address", "")),
                        ("报价截止", task.get("inquiry_deadline", "")),
                        ("快递单号", task.get("shipped_no", "")),
                        ("到货/最晚发货时间", task.get("latest_ship_time", "")),
                        ("验收时间", task.get("updated_at", "")),
                    ]
                    _g_detail = "\n".join(f"  {k}：{v}" for k, v in _g_rows if str(v or "").strip())
                    body_g_full = (
                        "您好，本次采购已确认验收并进入结算，现向贵司确认以下采购信息：\n\n"
                        "【本次采购确认详细信息】\n" + _g_detail
                    )
                    # 引用"供应商发货回执邮件"原文，使回复中可见之前的邮件流（回复目标即该发货邮件）
                    _sbody = (_smeta.get("body") or "").strip()
                    if _sbody:
                        body_g_full += "\n\n" + _quote_orig_body(_sbody)
                    subj_g = _safe_format(tpl_g.get("subject") or "", fmt_args)
                    # —— 全员回复供应商"带单号的发货回执邮件"：天然携带之前的邮件信息（引用原文由回复线程承接）——
                    g_reply_mid = _norm_mid(_smeta.get("msg_id") or "") or _norm_mid(task.get("e_mail_msg_id", "")) or reply_mid
                    # DB 优先取 References 链（发货回执 refs → E 存库链），缺时才 IMAP 兜底
                    reply_chain = (_smeta.get("refs") or "").strip() or (task.get("e_refs_chain") or "").strip()
                    if not reply_chain and g_reply_mid:
                        reply_chain = _fetch_sent_mail_refs(g_reply_mid) or ""
                    reply_chain = reply_chain or None
                    g_reply_all = {
                        "from_email": _smeta.get("from_email") or task.get("from_email", ""),
                        "to_email_list": _smeta.get("to_email_list") or [],
                        "cc_email_list": _smeta.get("cc_email_list") or [],
                    }
                    # 内部闭环仍需让工程师/审批人/全局抄送知情
                    g_cc = _external_flow_cc(task, cfg, exclude_to=(target_email,),
                                             extra_cc=((target_quote_g or {}).get("reply_all") or {}).get("cc_email_list") or [])
                    g_sent = tool_send_mail(to=[target_email], subject=subj_g, body_text=body_g_full,
                                            cc=g_cc or None,
                                            reply_to_mail_id=g_reply_mid or None,
                                            reply_refs_chain=reply_chain,
                                            reply_all_from=g_reply_all)
                    _archive_sent_mail(tid, "G", g_sent)
                spm.spare_mail_update_task(tid, {
                    "internal_status": "R_CLOSED",
                    "external_status": "R_WAIT_SETTLE",
                    "status": "DONE",
                    "latest_step": "R_APPROVAL→R_CLOSED(工程师验收通过, settlement(G) sent, 外部流→R_WAIT_SETTLE)",
                })
                return True

    if changed:
        return True
    spm.spare_mail_update_task(tid, {
        "latest_step": "R_APPROVAL(waiting for approver confirm / engineer completion)",
    })
    return False


def _mi_step_external(task: dict, cfg: dict, tpls: dict) -> bool:
    """外部流：按 external_status 推进。返回 True 表示该任务发生了状态迁移。"""
    st = task.get("external_status") or "R_SEND"
    if st == "R_SEND":
        return _step_sending_b(task, cfg, tpls)
    if st == "R_WAIT_QUOTES":
        return _step_waiting_quotes(task, cfg, tpls)
    if st == "R_DECIDING":
        return _step_deciding_lowest(task, cfg, tpls)
    if st == "R_ORDER":
        # 等内部审批确认 target_supplier 后再下订货 E
        if not (task.get("target_supplier") or ""):
            return False
        return _step_ordering(task, cfg, tpls)
    if st == "R_WAIT_SHIPPING":
        return _mi_step_wait_shipping(task, cfg, tpls)
    if st == "R_WAIT_ACCEPTANCE":
        # 收货待测试（采购确认）：等内部流工程师验收回执，验收通过后由内部流把外部流推进到 R_WAIT_SETTLE
        return False
    if st == "R_WAIT_SETTLE":
        # 已通知供应商结算、等待结算：终态，无进一步动作
        return False
    return False


def _mi_step_wait_shipping(task: dict, cfg: dict, tpls: dict) -> bool:
    """外部流 R_WAIT_SHIPPING：等选中供应商在 E 订货线程回复快递单号 → 存 shipped_no → R_WAIT_ACCEPTANCE。
    收到单号后进入"收货待测试（采购确认）"，等内部流工程师验收通过再推进到 R_WAIT_SETTLE 并发结算。
    """
    tid = task["task_id"]
    target = task.get("target_supplier", "")
    if task.get("shipped_no"):
        # 已登记过单号，进入收货待测试（不再直接闭环）
        _ensure_mail_inquiry_imports._spm.spare_mail_update_task(tid, {
            "external_status": "R_WAIT_ACCEPTANCE",
            "latest_step": "R_WAIT_SHIPPING→R_WAIT_ACCEPTANCE(收货待测试/采购确认)",
        })
        return True
    if not target:
        return False

    reply_mids = []
    for q in _safe_json_loads(task.get("quotes_json") or "[]"):
        if q.get("supplier") == target and q.get("email"):
            m = _norm_mid(q.get("msg_id", ""))
            if m:
                reply_mids.append(m)
            break
    e_mid = _norm_mid(task.get("e_mail_msg_id", ""))
    if e_mid:
        reply_mids.append(e_mid)
    if not reply_mids:
        return False

    since_ts = int(time.time()) - _DEFAULT_SINCE_MINUTES * 60 * 2
    exclude = [str(cfg.get("proc_mail_username") or "").strip()] if cfg.get("proc_mail_username") else None
    r = _tick_cached_read_inbox(since_timestamp=since_ts, exclude_sender_email_list=exclude,
                             match_in_reply_to_msg_ids=reply_mids)
    if not r.get("success"):
        return False

    spm = _ensure_mail_inquiry_imports._spm
    target_senders = {str(q.get("email") or "").lower() for q in
                      _safe_json_loads(task.get("quotes_json") or "[]")
                      if q.get("supplier") == target and q.get("email")}
    asked = bool(task.get("shipped_ask_sent") or "")
    seen_reply_no_no = False   # 目标供应商回了发货回执但没带单号
    ask_to = ""
    for m in r.get("mails", []):
        from_email = str(m.get("from_email") or "").lower().strip()
        if from_email not in target_senders:
            continue
        body = (m.get("mail_body_text") or "") + "\n" + (m.get("subject") or "")
        if re.search(r"单号|快递单号|物流单号|运单号", body):
            m_no = re.search(r"([A-Za-z]{0,6}[\d]{6,})", body)
            shipped_no = m_no.group(1).strip() if m_no else "".join(
                re.findall(r"[A-Za-z0-9-]{6,}", body)[:1])
            # 记录"带单号的发货回执邮件"的 message_id、References、正文与收/抄送人，供 G 全员回复用（DB 优先，不再现取邮箱）
            m_message_id = _norm_mid(m.get("message_id", ""))
            shipped_mail_meta = json.dumps({
                "msg_id": m_message_id,
                "refs": (m.get("references") or "").strip(),
                "from_email": m.get("from_email", ""),
                "to_email_list": m.get("to_email_list") or [],
                "cc_email_list": m.get("cc_email_list") or [],
                "body": (m.get("mail_body_text") or "")[:3000],
            }, ensure_ascii=False)
            spm.spare_mail_update_task(tid, {
                "external_status": "R_WAIT_ACCEPTANCE",
                "shipped_no": shipped_no,
                "shipped_mail_meta": shipped_mail_meta,
                "latest_step": f"R_WAIT_SHIPPING→R_WAIT_ACCEPTANCE(收货待测试/采购确认, shipped_no={shipped_no})",
            })
            return True
        # 收到供应商回执但正文未给出快递单号 → 标记需主动索取
        seen_reply_no_no = True
        ask_to = from_email

    # 缺陷修复：供应商回"已发货"但没带单号 → 主动发邮件请其补充（只发一次，防每 tick 重复）
    if seen_reply_no_no and not asked and ask_to:
        _neu = _task_neu_no(task)
        tool_send_mail(
            to=[ask_to],
            subject=f"Re: 【订货确认】请补充快递单号 [{_neu}]",
            body_text=(
                f"您好，已收到贵司关于任务 {_neu} 的发货回执，但邮件中未看到快递单号。\n\n"
                "请直接回复本邮件补上快递单号（例如：SF123456789），"
                "以便我方登记物流并跟踪到货验收。\n\n- NeuOps 备件邮件询价系统"
            ),
            reply_to_mail_id=e_mid or None,
        )
        spm.spare_mail_update_task(tid, {
            "shipped_ask_sent": "1",
            "latest_step": "R_WAIT_SHIPPING(asked supplier to supply courier no)",
        })
        return False

    spm.spare_mail_update_task(tid, {"latest_step": "R_WAIT_SHIPPING(waiting courier no)"})
    return False


# ════════════════════════════════════════════════════════════════
# 调试 / 管理端点（不新增 config 表、不暴露敏感字段）
# ════════════════════════════════════════════════════════════════

@router.post("/mail-inquiry/task/{task_id}/advance")
async def mail_inquiry_advance_task(task_id: str, to_status: str = "DECIDING_LOWEST", body: dict = None):
    """手动推进单个任务到指定状态（调试/应急用，绕过等待供应商回复）。

    to_status 支持 DECIDING_LOWEST（把已收到的报价送去算最低价）。后续 tick 会继续推进。
    body 可选传 quotes=[{supplier,email,unit_price,condition,count,ship_time,...}]，
    会先覆盖写入任务报价再推进（用于报价解析失败但人工已读出的场景）。
    """
    body = body or {}
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    spm = _ensure_mail_inquiry_imports._spm
    t = spm.spare_mail_get_task(task_id)
    if not t:
        return {"success": False, "error": "not_found"}
    # 可选：人工注入报价
    inject = body.get("quotes")
    if inject is not None:
        spm.spare_mail_update_task(task_id, {"quotes_json": json.dumps(inject, ensure_ascii=False)})
        t = spm.spare_mail_get_task(task_id)
    cfg, tpls = _load_mail_inquiry_skill()
    if to_status == "DECIDING_LOWEST":
        # 把已收的报价送去最低价优选
        ok = _step_deciding_lowest(t, cfg or {}, tpls or {})
        return {"success": bool(ok), "advanced_to": "DECIDING_LOWEST",
                "msg": "已推进到最低价优选，报价已汇总，后续 tick 会继续审批流程" if ok else "推进失败"}
    return {"success": False, "error": f"unsupported to_status={to_status}"}


@router.post("/mail-inquiry/tasks/clear")
async def mail_inquiry_clear_tasks():
    """清空全部备件邮件询价任务（调试/测试用）。"""
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    n = _ensure_mail_inquiry_imports._spm.spare_mail_delete_all_tasks()
    return {"success": True, "deleted": n}


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
    """幂等注册「备件邮件询价」能力到 emp-008（方案A：保留008统一入口，双流并入008）。

    不再新建独立数字员工 emp-mail-inquiry；把 skill-proc-mail-inquiry 绑定给 emp-008，
    使 emp-008 成为同时承载 chat(页面/对话) 与 邮件双流询价 的唯一备件采购数字员工。
    同时停用旧 emp-mail-inquiry 记录（避免平台出现两个）。
    """
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 【恢复传统状态机 2026-08-30】现轨 emp-008 重新启用为统一备件采购数字员工
    #（页面/对话/邮件三入口；本体轨 emp-009 保留但不接管）。保留记录可回退。
    emp_008 = {
        "id": "emp-008",
        "name": "备品备件采购询比价专员",
        "desc": "统一备件采购数字员工：支持 页面/Agent对话/工程师邮件 三入口。邮件双流引擎(skill-proc-mail-inquiry)负责工程师询价→报价→内部审批→订货→回单→结算全流程；chat 负责对话创建与进度查询。",
        "type": "采购询比价",
        "created": "2026-08-21",
        "updated": now_str,
        "rag_kb": "采购知识库-询比价流程与邮件模板",
        "prompt": "你是备品备件采购询比价专员（emp-008），统一处理三入口采购：页面/Agent对话/工程师邮件。",
        "model": "deepseek-v4",
        "skills": ["skill-proc-chat", "skill-proc-mail-compose", "skill-proc-parse",
                   _SKILL_ID_MAIL_INQUIRY],
        "skill_states": {"skill-proc-chat": True, "skill-proc-mail-compose": True,
                         "skill-proc-parse": True, _SKILL_ID_MAIL_INQUIRY: True},
        "enabled": True,
    }
    _ensure_mail_inquiry_imports._upsert_emp(emp_008)
    # 2) 停用旧 emp-mail-inquiry（方案A：不再作为独立数字员工暴露）
    try:
        _ensure_mail_inquiry_imports._upsert_emp({
            "id": "emp-mail-inquiry", "name": "备件邮件询价数字员工",
            "desc": "（已并入 emp-008，此记录停用）双流邮件询价能力由 emp-008 统一承载。",
            "type": "digital_employee", "created": "2026-08-28", "updated": now_str,
            "rag_kb": "", "prompt": "", "model": "",
            "skills": [_SKILL_ID_MAIL_INQUIRY],
            "skill_states": {_SKILL_ID_MAIL_INQUIRY: True},
            "enabled": False,
        })
    except Exception as e:
        print(f"[mail-inquiry] disable emp-mail-inquiry fallback: {e}")
    return {"success": True, "employee_id": "emp-008", "skill_id": _SKILL_ID_MAIL_INQUIRY,
            "note": "双流并入emp-008，停用emp-mail-inquiry"}


# ── 配置管理 API（spare_mail_config：邮件/飞书凭据、审批人、供应商、模板）──

def _ensure_mail_inquiry_config_seeded():
    """首次访问时，把 skill JSON 里的默认参与方/模板下沉到 DB（仅当对应 key 不存在时）。

    幂等：已有配置不覆盖，保证页面修改不被回滚。
    """
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    spm = _ensure_mail_inquiry_imports._spm
    cfg, tpls = _load_mail_inquiry_skill()
    if cfg:
        participants = {"approver_emails": cfg.get("approver_emails") or [],
                        "default_suppliers": cfg.get("default_suppliers") or []}
        if spm.spare_mail_get_config("proc_participants") is None:
            spm.spare_mail_set_config("proc_participants", participants)
    if tpls:
        if spm.spare_mail_get_config("proc_templates") is None:
            spm.spare_mail_set_config("proc_templates", tpls)
    return spm


@router.get("/mail-inquiry/config")
async def mail_inquiry_get_config(mask: bool = True):
    """读取配置汇总。mask=True 时对密码类字段打码（默认）。"""
    spm = _ensure_mail_inquiry_config_seeded()
    creds = spm.spare_mail_get_config("proc_credentials") or {}
    participants = spm.spare_mail_get_config("proc_participants") or {}
    templates = spm.spare_mail_get_config("proc_templates") or {}
    out_creds = dict(creds)
    if mask:
        for k in ("mail_password", "feishu_app_secret", "feishu_bitable_app_token"):
            if out_creds.get(k):
                v = str(out_creds[k])
                out_creds[k] = v[:2] + "****" if len(v) > 4 else "****"
    return {
        "success": True,
        "credentials": out_creds,
        "participants": participants,
        "templates": templates,
        "mail_configured": bool((creds or {}).get("mail_password")),
    }


@router.put("/mail-inquiry/config")
async def mail_inquiry_put_config(body: dict):
    """更新配置：段级覆盖。body 支持 {credentials, participants, templates} 或 {section, value}。

    - credentials: 邮件/飞书凭据键（mail_username/mail_password/imap_host/...）
    - participants: {approver_emails, default_suppliers}
    - templates: {A: {subject, body/name}, B: ...}
    """
    _ensure_mail_inquiry_imports()
    _ensure_mail_inquiry_imports._init_db()
    spm = _ensure_mail_inquiry_imports._spm
    if not body or not isinstance(body, dict):
        return {"success": False, "error": "body_required"}

    # 段级快捷写法：{section:"credentials|participants|templates", value:{...}}
    section = body.get("section")
    value = body.get("value")
    if section in ("credentials", "participants", "templates"):
        body = {section: value or {}}

    def _merge(target: dict, patch: dict) -> dict:
        merged = dict(target or {})
        for k, v in (patch or {}).items():
            # 空字符串视为清空该键，None 忽略
            if v is None:
                continue
            merged[k] = v
        return merged

    if "credentials" in body:
        cur = spm.spare_mail_get_config("proc_credentials") or {}
        new = _merge(cur, body.get("credentials") or {})
        spm.spare_mail_set_config("proc_credentials", new)
    if "participants" in body:
        cur = spm.spare_mail_get_config("proc_participants") or {}
        new = _merge(cur, body.get("participants") or {})
        spm.spare_mail_set_config("proc_participants", new)
    if "templates" in body:
        cur = spm.spare_mail_get_config("proc_templates") or {}
        new = _merge(cur, body.get("templates") or {})
        spm.spare_mail_set_config("proc_templates", new)
    return {"success": True, "msg": "配置已更新", "reload_required": False}
