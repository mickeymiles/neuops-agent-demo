# -*- coding: utf-8 -*-
"""PM 域工具数据源回归：★不得返回 MOCK 假数据（P-2026-*）。

历史缺陷：pm_project_read / pm_task_read / pm_workhour_read / pm_cost_calc 直接读
mock_data 的 MOCK_PM_*（虚构项目 P-2026-001 等），智能体据此作答 → 用户看到假项目
与假成本。2026-09-05 按「9007 必须用本体数据」改造：项目/成本改读共享 ontos ABox，
工时/任务显式返回 not_available（未接入），绝不编造。

本用例用临时业务库 + monkeypatch 注入 DB 路径，断言：
1. pm_project_read / pm_cost_calc 返回本体真实数据（source=ontos）
2. pm_task_read / pm_workhour_read 返回 not_available，且不含任何 P-2026 假数据
3. 任何响应里都不出现 P-2026-*（全局红线断言）
"""
import json
import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

import mcp_gateway

# 共享 ontos 子模块位于 <repo>/ontos（内含 ontos/ 包）
_ONTOS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ontos'))
if _ONTOS_ROOT not in sys.path:
    sys.path.insert(0, _ONTOS_ROOT)

from ontos.domain_business import COST_FORMULA_POLICY

AB = COST_FORMULA_POLICY["abox_adapter"]

FAKE_IDS = ("P-2026",)   # 假项目编号前缀（mock_data.MOCK_PM_PROJECTS）


@pytest.fixture(scope="module")
def biz_db(tmp_path_factory):
    """临时业务库：一条真实形态的项目主数据"""
    p = str(tmp_path_factory.mktemp("biz") / "contract_compare.db")
    conn = sqlite3.connect(p)
    cols = [AB["key"], AB["name"], AB["budget"], AB["current_cost"],
            AB["profile"]["dept"], AB["profile"]["owner"]]
    cols += list(COST_FORMULA_POLICY["budget"]["columns"].values())
    cols += list(COST_FORMULA_POLICY["cost"]["columns"].values())
    conn.execute('CREATE TABLE md_contract (%s)' % ','.join('"%s" TEXT' % c for c in cols))
    vals = {AB["key"]: "DFSY1410017C", AB["name"]: "银川市口腔医院迁建工程",
            AB["budget"]: 80596.58, AB["current_cost"]: 372782.88,
            AB["profile"]["dept"]: "大客户部", AB["profile"]["owner"]: "李四"}
    for c in COST_FORMULA_POLICY["budget"]["columns"].values():
        vals[c] = 26865
    for c in COST_FORMULA_POLICY["cost"]["columns"].values():
        vals[c] = 62130
    conn.execute('INSERT INTO md_contract (%s) VALUES (%s)' % (
        ','.join('"%s"' % c for c in cols), ','.join('?' * len(cols))),
        [vals[c] for c in cols])
    conn.commit()
    conn.close()
    return p


@pytest.fixture(autouse=True)
def _point_to_tmp_db(monkeypatch, biz_db):
    monkeypatch.setenv("ONTOS_DB_PATH", biz_db)


@pytest.fixture
def client():
    return TestClient(mcp_gateway.app)


def _assert_no_fake_data(payload: dict):
    """★红线断言：任何位置都不得出现 P-2026-* 假项目"""
    text = json.dumps(payload, ensure_ascii=False)
    for fake in FAKE_IDS:
        assert fake not in text, f"响应中出现演示假数据 {fake}*：{text[:300]}"


def test_pm_project_read_uses_ontology(client):
    r = client.post("/tools/pm_project_read", json={"project_id": "DFSY1410017C"})
    assert r.status_code == 200
    body = r.json()
    _assert_no_fake_data(body)
    assert body["success"] is True
    assert body["data_source"] == "ontos"
    p = body["data"]["projects"][0]
    assert p["project_id"] == "DFSY1410017C"
    assert p["contract_no"] == "DFSY1410017C"
    assert p["name"] == "银川市口腔医院迁建工程"
    assert p["dept"] == "大客户部"
    # 成本与本体判定（372782.88 / 80596.58 → 超支）
    assert p["budget"] == 80596.58 and p["current_cost"] == 372782.88
    assert p["cost_status"] == "超支"
    # ⌛四算未接入，且明确标注
    assert body["data"]["four_calc"]["available"] is False


def test_pm_project_read_unknown_id(client):
    r = client.post("/tools/pm_project_read", json={"project_id": "P-2026-001"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "合同编号" in body["data"]["error"]      # 提示真实编号形态


def test_pm_task_read_not_available(client):
    r = client.post("/tools/pm_task_read", json={"project_id": "DFSY1410017C"})
    body = r.json()
    _assert_no_fake_data(body)
    assert body["success"] is False
    assert body["data"]["tasks"] == []
    assert body["data"]["available"] is False
    assert "工单" in body["data"]["blocked_by"]


def test_pm_workhour_read_not_available(client):
    r = client.post("/tools/pm_workhour_read", json={"project_id": "DFSY1410017C"})
    body = r.json()
    _assert_no_fake_data(body)
    assert body["success"] is False
    assert body["data"]["records"] == []
    assert body["data"]["compliance_rate"] is None      # 不再编造合规率
    assert body["data"]["available"] is False
    assert "工时" in body["data"]["blocked_by"]


def test_pm_cost_calc_uses_ontology(client):
    r = client.post("/tools/pm_cost_calc", json={"project_id": "DFSY1410017C"})
    body = r.json()
    _assert_no_fake_data(body)
    assert body["success"] is True
    assert body["data_source"] == "ontos"
    c = body["data"]["costs"][0]
    # 分量列名取 COST_FORMULA_POLICY（单一真相）
    assert set(c["budget_items"]) == set(COST_FORMULA_POLICY["budget"]["columns"])
    assert set(c["cost_items"]) == set(COST_FORMULA_POLICY["cost"]["columns"])
    assert c["cost_status"] == "超支"


def test_biz_metric_read_marked_as_demo(client):
    """集团指标仍是演示数据，但必须被明确标记，不得冒充真实指标"""
    r = client.post("/tools/biz_metric_read", json={"metric_name": ""})
    body = r.json()
    assert body["data"]["data_status"]["demo"] is True
    assert body["data"]["data_status"]["available"] is False
    assert body["data_source"] == "mock"
