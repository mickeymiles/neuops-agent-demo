# -*- coding: utf-8 -*-
"""抄送策略回归护栏（业务约定：抄送 = 审批人 + 首封 A 抄送 + 系统配置抄送 + 本轮角色）。

背景：B 函（询价函）曾漏配审批人，只带 inquiry_cc + global_cc。
本文件固化「任何一封对外邮件的抄送都必须包含审批人」这一规则，
并锁定去重/去空/排除自身的行为，防止回归。
"""
import pytest

from app.ontology.execution import _cc_all

APPROVER = "biquanzhi5@163.com"
OBSERVER = "observer@corp.com"        # 首封 A 的抄送（观察员）
GLOBAL1 = "rich-miles@163.com"        # 系统配置抄送
GLOBAL2 = "biquanzhi@163.com"
STARTER = "biquanzhi1@163.com"        # 发起人（工程师）


def _ctx():
    return {
        "approver_emails": [APPROVER],
        "inquiry_cc": [OBSERVER],
        "global_cc": [GLOBAL1, GLOBAL2],
        "from_email": STARTER,
    }


def test_cc_all_contains_all_three_sources():
    """三路来源必须齐全：审批人 + 首封 A 抄送 + 系统配置抄送。"""
    cc = _cc_all(_ctx())
    assert APPROVER in cc, "抄送必须包含系统配置的审批人"
    assert OBSERVER in cc, "抄送必须包含首封 A 的抄送（全局携带）"
    assert GLOBAL1 in cc and GLOBAL2 in cc, "抄送必须包含系统配置抄送"


def test_cc_all_extra_role_appended():
    """E/G 等主送供应商时，发起人以 extra 形式进入抄送。"""
    ctx = _ctx()
    assert STARTER not in _cc_all(ctx), "无 extra 时发起人不应进抄送（D/F 的 To 就是发起人）"
    assert STARTER in _cc_all(ctx, ctx["from_email"]), "有 extra 时发起人应在抄送中"


def test_cc_all_dedup_and_drop_empty():
    """按邮箱小写去重，丢弃空值/None。"""
    ctx = {
        "approver_emails": ["A@x.com", "", None],
        "inquiry_cc": ["a@x.com", "A@x.com"],
        "global_cc": [None, "B@x.com", "  "],
        "from_email": "",
    }
    cc = _cc_all(ctx)
    assert cc == ["A@x.com", "B@x.com"], f"去重/去空不正确: {cc}"


def test_cc_all_excludes_self_email():
    """排除智能体自身邮箱，防止自激循环。"""
    ctx = _ctx()
    try:
        from app.ontology.execution import _self_email
    except Exception:
        pytest.skip("无法导入 _self_email")
    self_mail = _self_email()
    if not self_mail:
        pytest.skip("未配置本体轨邮箱，跳过")
    ctx["approver_emails"] = [self_mail.upper(), APPROVER]
    cc = _cc_all(ctx)
    assert APPROVER in cc
    assert all(a.lower() != self_mail.lower() for a in cc), "抄送不得包含智能体自身邮箱"


def test_no_bare_cc_concat_left_in_execution():
    """execution.py 中不得再有裸露的 inquiry_cc/global_cc/approver_emails 拼接。

    即所有抄送都必须经 _cc_all 构造，避免新增模板时漏配。
    """
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "app", "ontology", "execution.py")
    src = open(path, encoding="utf-8").read()
    offenders = [
        line.strip()
        for line in src.split("\n")
        if ("inquiry_cc" in line or "global_cc" in line or "approver_emails" in line)
        and line.strip().startswith("cc=")
        and "_cc_all" not in line
    ]
    assert not offenders, f"发现未走 _cc_all 的抄送拼接: {offenders}"
    assert src.count("cc=_cc_all(") >= 5, "B/D/E/F/G 五处模板都应使用 _cc_all"
