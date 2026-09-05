# -*- coding: utf-8 -*-
"""9010 网关 /tools/ontology_compute 传参兼容性回归测试。

背景缺陷（已修复）：
    该路由曾把 function / params 全部声明为 Query(...)，导致 POST JSON body
    里的 params 被**静默丢弃**——9006 用默认参数算出结果，且 success 仍为 true。
    表现为财务数字静默错误：roi 0.25 -> null、资金占用 250000 -> 0、
    cost_rollup 直接 param_error。这比显式报错危险得多。

修复：改为 body 优先、query 兜底；params 接受 dict 或 JSON 字符串。

架构变更（2026-09-05 用户拍板·同源）：
    网关不再 HTTP 转发 9006 /api/ontos/compute，改为本地 import 共享 ontos
    （app.ontos_compute.compute）。本用例用 TestClient + monkeypatch 捕获
    传给 compute 的 (function, params)，断言各种传参方式下 params 均正确透传
    （不依赖真实 9006 服务，也不需要真实业务库）。
"""
import json
import urllib.parse

import pytest
from fastapi.testclient import TestClient

import mcp_gateway

PARAMS = {"revenue": 1000000.0, "current_cost": 800000.0}

# 捕获 (function, params) 的假 ontos_compute.compute
_captured = []


def _fake_compute(function, params=None):
    _captured.append((function, params))
    return {"success": True, "function": function, "result": {"echo_params": params or {}}}


@pytest.fixture(autouse=True)
def _patch_compute(monkeypatch):
    _captured.clear()
    monkeypatch.setattr("app.ontos_compute.compute", _fake_compute)
    yield


@pytest.fixture
def client():
    return TestClient(mcp_gateway.app)


def _last_call():
    assert _captured, "未捕获到本体计算调用"
    return _captured[-1]


def test_post_body_only(client):
    """POST 仅用 JSON body 传 params —— 修复前此场景 params 静默丢失"""
    r = client.post("/tools/ontology_compute",
                    json={"function": "project_roi", "params": PARAMS})
    assert r.status_code == 200
    fn, params = _last_call()
    assert fn == "project_roi"
    assert params == PARAMS


def test_post_query_only(client):
    """POST 用 query 传 params（JSON 字符串，需 URL 编码）"""
    qs = urllib.parse.quote(json.dumps(PARAMS))
    r = client.post(f"/tools/ontology_compute?function=project_roi&params={qs}")
    assert r.status_code == 200
    assert _last_call()[1] == PARAMS


def test_post_body_precedes_query(client):
    """body 与 query 同时提供时，body 优先"""
    r = client.post("/tools/ontology_compute?function=project_roi&params={}",
                    json={"function": "project_roi", "params": PARAMS})
    assert r.status_code == 200
    assert _last_call()[1] == PARAMS


def test_get_query_only(client):
    """GET 用 query 传参（原有方式保持兼容）"""
    qs = urllib.parse.quote(json.dumps(PARAMS))
    r = client.get(f"/tools/ontology_compute?function=project_roi&params={qs}")
    assert r.status_code == 200
    assert _last_call()[1] == PARAMS


def test_no_params_defaults_to_empty(client):
    """不传 params 时退化为空 dict，不应抛异常"""
    r = client.post("/tools/ontology_compute", json={"function": "project_roi"})
    assert r.status_code == 200
    assert _last_call()[1] == {}


def test_malformed_params_json_falls_back(client):
    """params 传非法 JSON 字符串时容错为空 dict，不应 500"""
    r = client.post("/tools/ontology_compute?function=project_roi&params=not-json")
    assert r.status_code == 200
    assert _last_call()[1] == {}


def test_params_accepts_json_string_in_body(client):
    """body 里 params 传 JSON 字符串也应正确解析（LLM 常见用法）"""
    r = client.post("/tools/ontology_compute",
                    json={"function": "project_roi", "params": json.dumps(PARAMS)})
    assert r.status_code == 200
    assert _last_call()[1] == PARAMS


def test_response_source_is_ontos(client):
    """★同源契约：网关本地直调共享 ontos（data_source='ontos'），不再转发 9006。

    tool_response 内部把 source 参数映射为响应体的 data_source 字段（缺省为全局
    DATA_SOURCE=mock），故断言 data_source 而非 source。
    """
    r = client.post("/tools/ontology_compute",
                    json={"function": "project_cost_warning", "params": {"budget": 100}})
    assert r.status_code == 200
    body = r.json()
    assert body.get("data_source") == "ontos"
