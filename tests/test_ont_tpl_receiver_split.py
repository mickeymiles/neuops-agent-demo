# -*- coding: utf-8 -*-
"""emp-009 收货信息拆分 + 货期推算回归测试。

背景（用户需求）
──────────────
1. 模板E【收货信息】的 receiver_name/receiver_phone 原先写死默认值
   （运维部 / 请回复本会话提供），而工程师在模板A「收货地址」里
   常把收件人和电话一并写入。需要从地址串拆出：收货人 / 联系电话 / 纯地址。
2. 询价邮件（模板B）增加「货期：」行 —— 最晚发货日期 - 询价邮件日期，
   参考紧急程度算法（基准 = 邮件头 Date）；推算不出回退「按实际情况填写」。
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.ontology import mail_tpl
from app.ontology.orbit import _delivery_days


# ── split_receiver_info：地址串拆三字段 ─────────────────────────

def test_split_name_phone_appended_to_address():
    """典型：地址后跟 人名+手机号（空格分隔）。"""
    addr = "北京市海淀区软件园二期A区3号楼 张三 13800138000"
    name, phone, pure = mail_tpl.split_receiver_info(addr)
    assert name == "张三"
    assert phone == "13800138000"
    assert "张三" not in pure and "13800138000" not in pure
    assert pure.startswith("北京市海淀区")


def test_split_labeled_style():
    """标签式：收货人：/电话：/地址： 逗号分隔。"""
    addr = "收货人：李四，电话：139-1234-5678，地址：上海市浦东新区世纪大道100号"
    name, phone, pure = mail_tpl.split_receiver_info(addr)
    assert name == "李四"
    assert phone == "13912345678"          # 清洗掉连字符
    assert "李四" not in pure and "139" not in pure
    assert "世纪大道100号" in pure
    assert "收货人" not in pure and "电话" not in pure and "地址" not in pure


def test_split_landline():
    """座机号码也应识别并剥离。"""
    addr = "广州市天河区体育西路55号 王五 020-88889999"
    name, phone, pure = mail_tpl.split_receiver_info(addr)
    assert name == "王五"
    assert phone == "020-88889999"
    assert "020-88889999" not in pure


def test_split_address_only_keeps_default():
    """纯地址（无人名电话）：拆分结果为空，字段回退默认值由调用方处理。"""
    addr = "深圳市南山区科技园南区R2栋"
    name, phone, pure = mail_tpl.split_receiver_info(addr)
    assert name == "" and phone == ""
    assert pure == addr


def test_split_no_name_glued_to_phone():
    """人名与地址无分隔符粘连（…3号楼张三138…）：宁缺毋滥，不误拆地址片段。"""
    addr = "北京市海淀区中关村大街1号A座1101室赵六13800138000"
    name, phone, pure = mail_tpl.split_receiver_info(addr)
    assert phone == "13800138000"
    assert name == ""                    # 「楼赵六」含地址后缀字 → 拒判
    assert "13800138000" not in pure
    assert pure.startswith("北京市海淀区")


def test_split_empty_and_none():
    assert mail_tpl.split_receiver_info("") == ("", "", "")
    assert mail_tpl.split_receiver_info(None) == ("", "", "")


# ── _delivery_days：货期 = 最晚发货日期 - 询价邮件日期 ───────────

def _mail_on(date_str):
    return {"date": date_str}


def test_delivery_days_basic():
    """9/1 发询价，9/4 最晚发货 → 3天。"""
    mail = _mail_on("Tue, 01 Sep 2026 10:00:00 +0800")
    assert _delivery_days(mail, "2026-09-04") == "3天"


def test_delivery_days_same_day_returns_empty():
    """当天发货不足 1 天 → 视为无法推算（回退默认文案）。"""
    mail = _mail_on("Tue, 01 Sep 2026 10:00:00 +0800")
    assert _delivery_days(mail, "2026-09-01") == ""


def test_delivery_days_cross_month_and_formats():
    mail = _mail_on("Tue, 30 Sep 2026 10:00:00 +0800")
    assert _delivery_days(mail, "2026-10-05") == "5天"
    assert _delivery_days(mail, "2026/10/5") == "5天"
    assert _delivery_days(mail, "2026年10月5日") == "5天"


def test_delivery_days_partial_rounds_up():
    """不足整天向上取整：9/1 10:00 → 9/3（跨 1.58 天）→ 2天。"""
    mail = _mail_on("Tue, 01 Sep 2026 10:00:00 +0800")
    assert _delivery_days(mail, "2026-09-03") == "2天"


def test_delivery_days_missing_or_garbage():
    """缺最晚发货时间 / 无法解析 → 空串（模板层回退「按实际情况填写」）。"""
    mail = _mail_on("Tue, 01 Sep 2026 10:00:00 +0800")
    assert _delivery_days(mail, "") == ""
    assert _delivery_days(mail, "尽快") == ""
    assert _delivery_days(mail, None) == ""


# ── build_fields：字段优先级与兜底 ──────────────────────────────

def _task(meta):
    return {"task_id": "OT-TEST", "spare_info": meta}


def test_build_fields_receiver_split_fallback():
    """地址串含人名电话 → E 模板三字段取拆分结果，地址为纯地址。"""
    ctx, task = {}, _task({
        "address": "北京市海淀区软件园二期A区3号楼 张三 13800138000",
    })
    f = mail_tpl.build_fields(ctx, task)
    assert f["receiver_name"] == "张三"
    assert f["receiver_phone"] == "13800138000"
    assert f["address"] == "北京市海淀区软件园二期A区3号楼"


def test_build_fields_receiver_meta_priority():
    """邮件按标签显式解析出的 receiver_name/phone 优先于地址拆分。"""
    ctx, task = {}, _task({
        "receiver_name": "王工", "receiver_phone": "13700000000",
        "address": "北京市海淀区某路1号 张三 13800138000",
    })
    f = mail_tpl.build_fields(ctx, task)
    assert f["receiver_name"] == "王工"
    assert f["receiver_phone"] == "13700000000"
    # 地址仍按拆分后的纯地址渲染
    assert f["address"] == "北京市海淀区某路1号"


def test_build_fields_receiver_default_when_no_phone():
    """拆不出任何信息 → 保留原默认值，地址原样。"""
    ctx, task = {}, _task({"address": "深圳市南山区科技园R2栋"})
    f = mail_tpl.build_fields(ctx, task)
    assert f["receiver_name"] == "运维部"
    assert f["receiver_phone"] == "（请回复本会话提供）"
    assert f["address"] == "深圳市南山区科技园R2栋"


def test_build_fields_delivery_days():
    ctx, task = {}, _task({"delivery_days": "3天"})
    assert mail_tpl.build_fields(ctx, task)["delivery_days"] == "3天"
    # 无货期信息 → 默认文案（需求：没写货期时默认按实际情况填写）
    assert mail_tpl.build_fields({}, _task({}))["delivery_days"] == "按实际情况填写"


def test_render_template_b_contains_delivery_days():
    """B 模板渲染后应包含货期行（skill JSON 已带 - 货期：{delivery_days}）。"""
    ctx, task = {}, _task({"delivery_days": "3天", "brand": "Seagate", "pn": "ST-1",
                           "count": "1", "urgent": "2h"})
    subj, body = mail_tpl.render("B", ctx, task)
    assert "- 货期：3天" in body
    assert "NeuAgent 备件采购智能体" in body
    assert "NeuOps" not in body
