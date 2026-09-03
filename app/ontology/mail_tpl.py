# -*- coding: utf-8 -*-
"""本体轨邮件模板渲染（emp-009，独立于现轨 routes_procurement_agent）。

复用 skill-proc-mail-inquiry 的 A-G 模板（skill JSON 为主源，9006 页面自定义最高优先），
提供：安全 format 渲染、原文引用（=== 分隔，比 `>` 在 webmail 更稳定）、
内外流收件人/Reply-All 辅助。只读复用，不改动现轨文件。
"""
import re
from datetime import datetime


def load_templates():
    """加载 A-G 邮件模板：skill JSON 为主源；DB 遗留行与文件兜底仅补缺失；9006 页面自定义最高优先。

    层级（高 → 低）：
      1. 9006「邮件模板」页面自定义（procurement_mail_template，只覆盖非空字段）
      2. skill JSON（skills/skill-proc-mail-inquiry.json，唯一维护源，mtime 热加载）
      3. DB `spare_mail_config.proc_templates` —— **历史迁移遗留快照**，全库无写入方，
         旧行会冻结旧模板盖掉 JSON 的新措辞（签名/货期行改了不生效的根因），
         故降级为"仅补 JSON 缺失的模板"，不再覆盖。
    """
    tpls = {}
    # 主源：skill_loader（注意旧代码误写 `from app.utils import load_skill`，
    # 该模块不存在 → ImportError 被吞 → 主加载路径从未生效，只剩文件兜底）
    try:
        from app.skill_loader import load_skill
        sk = load_skill("skill-proc-mail-inquiry") or {}
        skill_def = sk.get("skill") or {}
        tpls = dict(skill_def.get("templates") or {}) or dict(sk.get("templates") or {})
    except Exception:
        tpls = {}
    # 兜底：直接读 skill JSON 文件，确保 A-G 齐全（部分装载源可能缺宏模板 G）
    for want in ("A", "B", "C", "D", "E", "F", "G"):
        if want in tpls:
            continue
        try:
            import json
            import os
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "..", "skills", "skill-proc-mail-inquiry.json")
            with open(os.path.normpath(p), encoding="utf-8") as f:
                fj = json.load(f)
            ptpl = ((fj.get("skill") or {}).get("templates") or {}) or (fj.get("templates") or {})
            if want in ptpl:
                tpls[want] = ptpl[want]
        except Exception:
            pass
    # 遗留 DB 行：仅补缺失（不覆盖 JSON —— 见 docstring 第 3 层说明）
    try:
        from app.db.spare_mail import spare_mail_get_config
        db = spare_mail_get_config("proc_templates") or {}
        if isinstance(db, dict):
            for k, v in db.items():
                if v and k not in tpls:
                    tpls[k] = v
    except Exception:
        pass
    # 最高优先级：9006「邮件模板」页面维护的自定义模板
    # 只覆盖非空字段 —— subject/body 留空的模板仍用 skill 默认，避免发出空邮件
    try:
        from app.db import proc_9006_config as p9
        page_tpls = p9.load_mail_templates() or {}
        if page_tpls:
            merged = dict(tpls)
            for k, v in page_tpls.items():
                base = dict(merged.get(k) or {})
                if v.get("subject"):
                    base["subject"] = v["subject"]
                if v.get("body"):
                    base["body"] = v["body"]
                merged[k] = base
            tpls = merged
    except Exception:
        pass
    return tpls or {}


def _safe_format(template: str, args: dict) -> str:
    if not template:
        return ""
    try:
        return template.format(**args)
    except (KeyError, ValueError):
        def _repl(m):
            k = m.group(1)
            return str(args.get(k, ""))
        return re.sub(r"\{(\w+)\}", _repl, template)


def quote_orig(body: str, max_chars: int = 3000) -> str:
    """将原邮件正文以 === 引用分隔块追加到回复末尾，避免无限嵌套截断。"""
    body = str(body or "").strip()
    if not body:
        return ""
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


def _supplier_name_map():
    """构建 {email: 名称} 映射，供邮件正文显示供应商实名。

    唯一来源 = 9006「供应商」页维护的主数据（procurement_supplier）。
    不再回退 ONT_SUPPLIERS 环境变量 —— 避免配置来源二义。"""
    try:
        from app.db import proc_9006_config as p9
        return p9.supplier_name_map() or {}
    except Exception:
        return {}


# ── 收货地址拆分（模板E【收货信息】三字段）─────────────────────
# 工程师在模板A的「收货地址」里常把收件人和电话一并写入，例如：
#   "北京市海淀区软件园二期A区3号楼 张三 13800138000"
#   "收货人：张三，电话：13800138000，地址：北京市海淀区xx路xx号"
# E 模板需要拆出 receiver_name / receiver_phone / 纯 address 三个字段。
_PHONE_PATS = [
    re.compile(r"1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}"),   # 手机号（含 138-0013-8000 写法）
    re.compile(r"0\d{2,3}-?\d{7,8}"),                # 座机（区号-号码）
]
_NAME_LABEL_RE = re.compile(r"(?:收货人|收件人|联系人|收件方)\s*[:：]\s*([\u4e00-\u9fa5·]{2,4})")
_LABEL_PREFIX_RE = re.compile(r"(?:收货人|收件人|联系人|收件方|收货电话|联系电话|联系方式|电话|手机号码|手机|地址)\s*[:：]\s*")
# 人名候选若含地址后缀字（路/街/号/区…）视为误把地址片段当人名
_ADDR_SUFFIX_CHARS = set("路街号区园座楼室道巷镇县村厦栋单元层省市")


def _clean_phone(raw_phone: str) -> str:
    """手机号去掉空格/连字符（138-0013-8000 → 13800138000）；座机保持原样。"""
    digits = re.sub(r"\D", "", raw_phone)
    return digits if len(digits) == 11 and digits[:2] in (
        "13", "14", "15", "16", "17", "18", "19") else raw_phone


def split_receiver_info(address: str):
    """从收货地址串拆出 (收货人, 联系电话, 纯地址)。

    拆不出的字段返回空串（调用方回退默认值）；地址 = 去掉人名/电话/标签后的原串。
    """
    raw = str(address or "").strip()
    if not raw:
        return "", "", ""
    phone, phone_raw, phone_span = "", "", None
    for pat in _PHONE_PATS:
        m = pat.search(raw)
        if m:
            phone_raw, phone_span = m.group(0), m.span()
            phone = _clean_phone(phone_raw)
            break
    name = ""
    m = _NAME_LABEL_RE.search(raw)
    if m:
        name = m.group(1)
    elif phone_span:
        # 无标签时取电话前邻 2-4 个汉字：要求与地址之间有分隔符/非汉字边界，
        # 且不包含路/街/号等地址后缀字（防把"…3号楼张三"整段误当人名）。
        head = raw[:phone_span[0]]
        m2 = re.search(r"(?:^|[^\u4e00-\u9fa5])([\u4e00-\u9fa5·]{2,4})[\s,，、;；/()（）-]*$", head)
        if m2 and not (_ADDR_SUFFIX_CHARS & set(m2.group(1))):
            name = m2.group(1)
    # 纯地址：按电话原匹配串的 span 剥离（清洗后的号码可能带不出原串），
    # 人名可能在电话前后，先按位置删除再收敛残留分隔符。
    if phone_span:
        lo, hi = phone_span
        pure = raw[:lo] + " " + raw[hi:]
    else:
        pure = raw
    pure = _LABEL_PREFIX_RE.sub("", pure)
    if name:
        pure = pure.replace(name, "", 1)
    pure = re.sub(r"[\s,，、;；]{2,}", " ", pure).strip(" ,，、;；")
    return name, phone, pure


def build_fields(ctx: dict, task: dict, supplier_names: dict = None) -> dict:
    """把任务事实（ctx/task）映射为模板占位符取值。
    supplier_names：可选 {email: 实名} 映射（如 中软国际/神州数码），缺省回退 ONT_SUPPLIERS 解析。"""
    sname = supplier_names if isinstance(supplier_names, dict) else _supplier_name_map()
    meta = task.get("spare_info") or {}
    quotes = [q for q in (meta.get("quotes") or []) if q.get("unit_price")]
    target = str(ctx.get("target_supplier") or meta.get("target_supplier") or "")
    lowest = min(quotes, key=lambda q: float(q.get("unit_price") or 1e18)) if quotes else None
    target_quote = next((q for q in quotes if str(q.get("email") or "") == target), None)
    def _sn(email):
        return sname.get(str(email or "").strip().lower(), email or "")
    suppliers_str = "\n".join(
        f"{i + 1}. {_sn(q.get('email', ''))}（{q.get('email', '')}）  单价 {q.get('unit_price', '')}元"
        for i, q in enumerate(quotes)) or "（暂无）"
    condition = ctx.get("condition") or meta.get("condition") or ""
    cond_disp = {"全新": "全新原装", "原厂翻新": "原厂翻新（带保修）",
                 "拆机二手": "拆机二手（无保修）"}.get(condition, condition)
    deadline = meta.get("quote_deadline") or ctx.get("quote_deadline") or ""
    approvers = ctx.get("approver_emails") or meta.get("approver_emails") or []
    # 收货三字段：工程师邮件按标签解析的值优先 → 地址串拆分 → 系统默认值兜底
    raw_addr = str(meta.get("address") or ctx.get("address") or "")
    _s_name, _s_phone, _s_addr = split_receiver_info(raw_addr)
    receiver_name = str(meta.get("receiver_name") or "").strip() or _s_name or "运维部"
    receiver_phone = str(meta.get("receiver_phone") or "").strip() or _s_phone or "（请回复本会话提供）"
    # 货期：claim 时按「最晚发货日期 - 询价邮件日期」推算；推算不出回退默认文案
    delivery_days = str(meta.get("delivery_days") or ctx.get("delivery_days") or "").strip() or "按实际情况填写"
    base = {
        "project_no": meta.get("project_no") or ctx.get("project_no") or "",
        "project_name": meta.get("project_name") or ctx.get("project_name") or "",
        "part_type": meta.get("part_type") or ctx.get("part_type") or "",
        "brand": meta.get("brand") or ctx.get("brand") or "",
        "pn": meta.get("pn") or ctx.get("pn") or "",
        "spec": meta.get("spec") or ctx.get("spec") or "",
        "condition": condition, "condition_display": cond_disp,
        "count": meta.get("count") or ctx.get("count") or "",
        "address": _s_addr or raw_addr,
        "delivery_days": delivery_days,
        "urgent": meta.get("urgent") or meta.get("urgency_raw") or ctx.get("urgent") or "",
        "inquiry_dur": meta.get("urgent") or meta.get("urgency_raw") or ctx.get("urgent") or "",
        "latest_ship_time": meta.get("latest_ship_time") or ctx.get("latest_ship_time") or "",
        "deadline": deadline,
        "task_no": task.get("task_id") or "",
        "supplier": _sn(target),
        "suppliers": suppliers_str,
        "suppliers_count": len(quotes),
        "lowest_quote": f"¥{lowest.get('unit_price')}" if lowest else "",
        "lowest_supplier": _sn((lowest or {}).get("email", "")) if lowest else "",
        "approver_emails": "、".join(approvers),
        "quote": (target_quote or {}).get("unit_price", "") or (lowest or {}).get("unit_price", "") or "",
        "receiver_name": receiver_name, "receiver_phone": receiver_phone,
        "stop_reason": ctx.get("stop_reason") or "无供应商报价且已到询价截止",
        "body_placeholder": "",
    }
    return base


def render(key: str, ctx: dict, task: dict, supplier_names: dict = None):
    """渲染某模板，返回 (subject, body)。supplier_names 见 build_fields。"""
    tpl = (load_templates() or {}).get(key) or {}
    fields = build_fields(ctx, task, supplier_names=supplier_names)
    subj = _safe_format(tpl.get("subject") or "", fields)
    body = _safe_format(tpl.get("body") or "", fields)
    return subj, body


def reply_recipients(reply_from: dict, to, cc=None, self_email=""):
    """Reply-All：合并原邮件 To+Cc+From（排除系统自身），去重后返回 (to, cc)。
    用于外部流在供应商回复线程上全员回复。"""
    _self = {str(self_email or "").lower().strip()}
    cands = []
    cands += list((reply_from or {}).get("to_email_list") or [])
    cands += list((reply_from or {}).get("cc_email_list") or [])
    from_e = str((reply_from or {}).get("from_email") or "").lower().strip()
    if from_e and "@" in from_e:
        cands.append(from_e)
    cands = [a for a in dict.fromkeys(cands) if a and a.strip().lower() not in _self]
    to_extra = [a for a in cands if a not in [str(x).strip() for x in (to or [])]]
    final_to = list(dict.fromkeys([str(a).strip() for a in (to or [])] + to_extra))
    cc_list = list(dict.fromkeys([str(a).strip() for a in (cc or []) if a]))
    return final_to, cc_list