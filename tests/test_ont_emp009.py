# -*- coding: utf-8 -*-
"""NO-012 本体轨 emp-009 单元测试（独立于现轨测试）。
覆盖：独立 schema、emp-009 注册、动作/规则声明、决策提议、规则校验、审计追加。
"""
import os
import tempfile

_tmpdb = tempfile.mktemp(suffix=".db")
os.environ["ONT_DB_PATH"] = _tmpdb

import app.ontology as ont
ont.init()
from app.ontology import engine, store, actions, knowledge
from app.ontology.decision import propose_action, build_fact_context
from app.ontology.registration import register_emp009


def _full(**kv):
    d = {"task_id": "T1", "internal_status": "R_INIT", "external_status": "R_SEND",
         "project_no": "PRJ", "project_name": "p", "part_type": "硬盘", "brand": "Seagate",
         "pn": "ST", "spec": "1T", "condition": "全新", "count": "3", "address": "addr",
         "urgent": "5min", "quotes_json": "[]", "suppliers_json": "[]"}
    d.update(kv)
    return d


def test_emp009_registered():
    r = register_emp009()
    assert r["employee"] == "emp-009"
    assert r["skill"] == "skill-ont-proc-inquiry"


def test_action_registry():
    ids = actions.list_action_ids()
    assert "createTask" in ids and "engineerFinalClose" in ids


def test_rule_declarations():
    assert len(knowledge.RULES) >= 11
    assert any(r["id"] == "create_required" for r in knowledge.RULES)


def test_missing_fields_request():
    r = engine.evaluate_task(_full(pn=""))
    assert r["proposed_action"] == "requestMissingFields"


def test_created_distribute():
    r = engine.evaluate_task(_full(suppliers_json='[{"email": "s1@x.com"}]'))
    assert r["proposed_action"] == "distributeInquiry"


def test_abort_no_quote():
    r = engine.evaluate_task(_full(external_status="R_WAIT_QUOTES", latest_step="超时"))
    assert r["proposed_action"] == "abortTask"


def test_tracking_received():
    r = engine.evaluate_task(_full(external_status="R_ORDER", internal_status="R_APPROVAL",
                                   shipped_no="SF123"))
    assert r["proposed_action"] == "receiveTrackingNumber"


def test_tracking_missing_ask():
    r = engine.evaluate_task(_full(external_status="R_ORDER", internal_status="R_APPROVAL"))
    assert r["proposed_action"] == "requestTrackingNo"


def test_audit_append_only():
    before = len(store.list_audit(biz_type="Task", biz_id="T1"))
    store.audit("Task", "T1", "propose:createTask", operator="emp-009", snapshot={})
    rows = store.list_audit(biz_type="Task", biz_id="T1")
    assert len(rows) == before + 1
    assert rows[0]["action"].startswith("propose:")


def test_engine_end_to_end_alignment():
    r = engine.evaluate_task(_full())
    assert "proposed_action" in r
    assert r["dry_run"] is True