# -*- coding: utf-8 -*-
"""本体知识层（ontology.py）语义校验测试：验证 LLM 提议的动作只能命中可执行的语义动作，防重复/防回退。"""
import pytest

from app.ontology import ontology

SC = ontology.CONCEPTS
ACT = ontology.ACTIONS
INV = ontology.INVARIANTS


def _abox(**kw):
    base = {
        "task_id": "OT-X", "status": "INIT", "from_email": "eng@x.com",
        "internal_status": "R_INIT", "external_status": "R_SEND",
        "part": {"pn": "PN-1", "count": "2", "brand": "K", "part_type": "内存条", "condition": "全新",
                 "project_no": "P1", "project_name": "N", "spec": "s", "address": "a", "urgent": "5min"},
        "quotes": [], "quote_count": 0,
        "target_supplier_list": [], "inquiry_sent": False, "approval_sent": False,
        "target_supplier_set": False, "order_sent": False, "tracking_number": "",
        "engineer_feedback_finished": False, "deadline_passed": False,
    }
    base.update(kw)
    return base


def test_ontology_structure():
    # 每个动作都有定义 / 条件 / 效果 / 不变量 / 幂等
    for aid, spec in ACT.items():
        assert spec.get("定义"), aid
        assert isinstance(spec.get("条件"), list), aid
        assert isinstance(spec.get("效果"), str), aid
        assert spec.get("幂等") is True, aid
    assert INV, "应有全局不变量"


def test_distribute_ok_when_not_sent():
    ok, why = ontology.validate_action("distributeInquiry",
                                       _abox(target_supplier_list=["s2@x.com"], inquiry_sent=False))
    assert ok, why


def test_no_resend_inquiry():
    ok, why = ontology.validate_action("distributeInquiry",
                                       _abox(inquiry_sent=True, target_supplier_list=["s2@x.com"]))
    assert not ok, "已发过询价不得重复分发"
    assert any("不得重复" in r for r in why)


def test_no_order_before_approval():
    ok, why = ontology.validate_action("confirmOrderToSupplier", _abox())
    assert not ok, "无报价/未审批不得下订货"


def test_order_ok_when_approved():
    ok, why = ontology.validate_action(
        "confirmOrderToSupplier",
        _abox(quote_count=2, target_supplier_set=True, order_sent=False))
    assert ok, why


def test_no_duplicate_order():
    ok, why = ontology.validate_action(
        "confirmOrderToSupplier",
        _abox(quote_count=2, target_supplier_set=True, order_sent=True))
    assert not ok, "已下订不得重复"


def test_tracking_requires_order():
    ok, why = ontology.validate_action("receiveTrackingNumber", _abox(order_sent=False))
    assert not ok, "未下订货不得登记运单"
    ok2, _ = ontology.validate_action("receiveTrackingNumber", _abox(order_sent=True, tracking_number="SF1"))
    assert ok2


def test_no_close_before_shipment():
    ok, why = ontology.validate_action("engineerFinalClose",
                                       _abox(order_sent=True, tracking_number="", engineer_feedback_finished=True))
    assert not ok, "货未发/单未登记不得闭环"
    ok2, _ = ontology.validate_action(
        "engineerFinalClose",
        _abox(order_sent=True, tracking_number="SF1", engineer_feedback_finished=True))
    assert ok2