# -*- coding: utf-8 -*-
"""邮件正文解析工具（供应商报价 / 物流单号）。

历史：这些函数原先定义在 emp-008 现轨 `routes_procurement_agent.py` 里。
emp-008 现轨废弃删除后，由于 MCP 工具（`mcp_tools.tool_procurement_parse_quote` /
`tool_procurement_parse_logistics`）仍需要它们，故抽取为独立模块继续复用。

红线提醒：本体轨 emp-009 有自己的报价解析（`app/ontology/orbit._parse_quote`），
两者口径可能不同，勿混用。
"""
import re



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
