# -*- coding: utf-8 -*-
"""探针采集器测试：六类采集器返回统一 ProbeReport 结构"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.probe import (  # noqa: E402
    ApplicationCollector,
    BaseCollector,
    ContainerCollector,
    DatabaseCollector,
    MiddlewareCollector,
    NetworkCollector,
    ServerCollector,
)


def test_base_collector_abstract():
    # BaseCollector 不能直接实例化
    try:
        BaseCollector()
        assert False, "should raise TypeError"
    except TypeError:
        pass


def test_server_collector():
    rpt = ServerCollector().collect()
    assert isinstance(rpt.ok, bool)
    if rpt.ok:
        assert rpt.collector == "server"
        # 至少要有实体
        assert len(rpt.entities) > 0
        # CPU 指标
        metrics = {m[2] for m in rpt.metrics}
        assert "cpu_percent" in metrics


def test_database_collector():
    rpt = DatabaseCollector().collect()
    assert isinstance(rpt.ok, bool)
    assert rpt.collector == "database"


def test_middleware_collector():
    rpt = MiddlewareCollector().collect()
    assert isinstance(rpt.ok, bool)
    # 实体类型正确
    for e in rpt.entities:
        assert e["type"] == "middleware"


def test_network_collector():
    rpt = NetworkCollector().collect()
    assert isinstance(rpt.ok, bool)
    if rpt.ok:
        metrics = {m[2] for m in rpt.metrics}
        assert "listen_ports" in metrics


def test_application_collector():
    rpt = ApplicationCollector().collect()
    assert isinstance(rpt.ok, bool)
    names = {e["name"] for e in rpt.entities}
    # 至少 neuops 自身应被采集（9007）
    assert any("neuops" in n for n in names) or rpt.error


def test_container_collector_graceful():
    # 无 docker 环境也应优雅降级不崩溃
    rpt = ContainerCollector().collect()
    assert isinstance(rpt.ok, bool)
