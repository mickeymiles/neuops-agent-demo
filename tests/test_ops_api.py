# -*- coding: utf-8 -*-
"""/api/ops/* 接口测试：实体 / 拓扑 / 时序 / 配置 / 事件"""
# 规格编号: NO-001 探针状态 / NO-002 本体拓扑 / NO-003 告警规则 / NO-007 运维平台
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)


def test_ops_page():
    # 页面路由（浏览器入口 /ops）与 API 内页路由必须均可达
    r = client.get("/api/ops/page")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    r2 = client.get("/ops")
    assert r2.status_code == 200
    assert "text/html" in r2.headers.get("content-type", "")


def test_ops_overview():
    r = client.get("/api/ops/overview")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "entities" in d
    assert "probe" in d


def test_ops_entities():
    r = client.get("/api/ops/entities")
    assert r.status_code == 200
    assert isinstance(r.json()["entities"], list)


def test_ops_topology():
    r = client.get("/api/ops/topology")
    assert r.status_code == 200
    t = r.json()["topology"]
    assert isinstance(t["nodes"], list)
    assert isinstance(t["edges"], list)
    assert "summary" in t


def test_ops_settings_roundtrip():
    r = client.put("/api/ops/settings", json={"cpu_threshold": "85"})
    assert r.status_code == 200
    r2 = client.get("/api/ops/settings")
    s = r2.json()["settings"]
    assert s["cpu_threshold"]["value"] == "85"


def test_ops_metrics_query():
    r = client.get("/api/ops/metrics?minutes=5")
    assert r.status_code == 200
    assert isinstance(r.json()["metrics"], list)


def test_ops_probe_status():
    r = client.get("/api/ops/probe/status")
    assert r.status_code == 200
    assert "collectors" in r.json()


def test_ops_alert_rules():
    r = client.get("/api/ops/alert-rules")
    assert r.status_code == 200
    rules = r.json()["rules"]
    # 应包含真实系统指标规则
    metrics = {x["metric"] for x in rules}
    assert "cpu_percent" in metrics or "health" in metrics


def test_ops_alerts_aggregate():
    r = client.get("/api/ops/alerts/aggregate?status=all")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert isinstance(d["alerts"], list)


def test_monitor_redirect_to_ops():
    r = client.get("/monitor", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert r.headers.get("location", "").endswith("/ops")


def test_ops_probe_run_now():
    r = client.post("/api/ops/probe/run-now")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_monitor_topology_layer_direction():
    # NO-007 拓扑双链路布局：MCP 链 server→tool（承载）、RAG 链 agent→vector_db→kb（检索/承载）
    r = client.get("/api/monitor/topology")
    assert r.status_code == 200
    d = r.json()["data"]
    nodes = {n["id"]: n for n in d["nodes"]}
    edges = d["edges"]
    # 服务承载工具：server 边 SHALL 为 server → tool（不得出现 tool → server 旧方向）
    server_edges = [e for e in edges if e["type"] == "server"]
    assert server_edges, "拓扑缺少 server 边（MCP Server 承载 Tools）"
    for e in server_edges:
        assert nodes[e["source"]]["type"] == "server", f"server 边源节点应为 MCP Server: {e}"
        assert nodes[e["target"]]["type"] == "tool", f"server 边目标节点应为 Tool: {e}"
    # RAG 链：有知识库数据时验证 数字员工 → 向量数据库 → 知识库 方向
    if any(n["type"] == "kb" for n in nodes.values()):
        vec_edges = [e for e in edges if e["type"] == "vector"]
        assert vec_edges, "存在知识库但缺少 vector 边（向量数据库承载知识库）"
        for e in vec_edges:
            assert e["source"] == "chroma", f"vector 边源节点应为向量数据库 chroma: {e}"
            assert nodes[e["target"]]["type"] == "kb", f"vector 边目标节点应为知识库: {e}"
        kb_edges = [e for e in edges if e["type"] == "kb"]
        assert kb_edges, "存在知识库但缺少 kb 边（数字员工检索向量数据库）"
        for e in kb_edges:
            assert nodes[e["source"]]["type"] == "agent", f"kb 边源节点应为数字员工: {e}"
            assert e["target"] == "chroma", f"kb 边目标节点应为向量数据库 chroma: {e}"
        # 不得残留旧方向边：agent→kb / kb→chroma
        for e in edges:
            assert not (e["type"] == "kb" and e["target"] != "chroma"), f"残留旧方向 kb 边: {e}"
            assert not (e["type"] == "vector" and e["source"] != "chroma"), f"残留旧方向 vector 边: {e}"
