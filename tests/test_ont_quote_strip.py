# -*- coding: utf-8 -*-
"""携带原文回复（reply-all + 引用）不应干扰智能体的意图识别。

回归测试：审批人在『确认采购』的回复里携带了 D 邮件原文（含两供应商名称），
智能体必须只看审批人自己新写的内容，仍按最低价选 b6，而不是被引用的 b2 名称误导。
"""
import json
import os
import sys
import importlib
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import app.ontology.orbit as orbit  # noqa: E402


def _claimed_approval_choice(supplier_reply_body):
    """模拟 process_replies 的审批分支，返回 009 选定的 target_supplier。"""
    suppliers = [
        {"name": "中软国际", "email": "biquanzhi2@163.com"},
        {"name": "神州数码", "email": "biquanzhi6@163.com"},
    ]
    quotes = [
        {"email": "biquanzhi2@163.com", "unit_price": "1280"},
        {"email": "biquanzhi6@163.com", "unit_price": "980"},
    ]
    meta = {"quotes": quotes, "approver_emails": ["biquanzhi5@163.com"]}
    # 复用 orbit 的解析逻辑：剥离引用 + 选最低价（除非显式点名）
    body_new = orbit._strip_quoted(supplier_reply_body)
    if any(k in body_new for k in orbit._APPROVE_KW):
        qq = [q for q in quotes if q.get("email") and q.get("unit_price")]
        low = min(qq, key=lambda q: float(q.get("unit_price") or 10 ** 12)) if qq else None
        low_email = low["email"] if low else ""
        named = orbit._supplier_mentioned_in(body_new, suppliers)
        if named and named != low_email and any(str(q.get("email")) == named for q in qq):
            chosen = named
        else:
            chosen = low_email
        meta["target_supplier"] = chosen
        meta["approval_choice"] = chosen
    return meta.get("approval_choice")


def test_approval_ignores_quoted_supplier_names():
    # 审批回复携带 D 原文（含"中软国际/神州数码"），自己只写"确认采购，按比价最低价执行"
    d_original = (
        "尊敬的  审批人：\n以下是报价汇总，请确认选家：\n"
        "- 中软国际：1280 元\n- 神州数码：980 元\n任务编号：OT-TEST123"
    )
    reply = ("确认采购，按比价最低价执行。\n- 李审批\n\n"
             "----- 原始邮件 -----\n> 尊敬的  审批人：\n> 以下是报价汇总：\n"
             "> - 中软国际：1280 元\n> - 神州数码：980 元")
    assert _claimed_approval_choice(reply) == "biquanzhi6@163.com", \
        "携带原文后不应被引用的 b2 名称误导，应选最低价 b6"


def test_quote_strip_removes_gt_lines():
    body = "确认采购\n\n----- 原始邮件 -----\n> 中软国际 1280\n> 神州数码 980"
    stripped = orbit._strip_quoted(body)
    # 引用的供应商名称（> 行）必须被剥离，且不出现在新文本中
    assert "中软国际" not in stripped and "神州数码" not in stripped
    assert "确认采购" in stripped
    # 无引用时原样返回
    assert orbit._strip_quoted("直接回复，无引用") == "直接回复，无引用"
