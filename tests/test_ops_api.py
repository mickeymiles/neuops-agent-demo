# -*- coding: utf-8 -*-
"""/api/ops/* 接口测试：实体 / 拓扑 / 时序 / 配置 / 事件"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)


def test_ops_page():
    r = client.get("/api/ops/page")
    assert r.status_code in (200, 404)


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


def test_ops_incidents():
    r = client.get("/api/ops/incidents")
    assert r.status_code == 200
    assert isinstance(r.json()["incidents"], list)


def test_ops_alert_rules():
    r = client.get("/api/ops/alert-rules")
    assert r.status_code == 200
    rules = r.json()["rules"]
    # 应包含真实系统指标规则
    metrics = {x["metric"] for x in rules}
    assert "cpu_percent" in metrics or "health" in metrics


def test_ops_probe_run_now():
    r = client.post("/api/ops/probe/run-now")
    assert r.status_code == 200
    assert r.json()["ok"] is True
