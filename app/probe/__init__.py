# -*- coding: utf-8 -*-
"""统一监控探针（Unified Monitoring Probe）

一个探针解决所有采集问题：服务器 / 容器 / 数据库 / 中间件 / 应用 / 网络。
- 每个采集器(Collector)负责一类实体的真实采集（psutil / 系统命令 / HTTP 探测 / 端口探测）
- 探针管理器(ProbeManager)统一调度全部采集器，结果写入 ops_metrics / ops_entities / ops_relations
- 支持嵌入应用内运行，也支持独立 CLI 运行（远程探针预留）

用法：
    from app.probe import ProbeManager
    pm = ProbeManager()
    pm.run_once()          # 单轮全量采集
    pm.start()             # 后台线程，按配置周期持续采集
    pm.stop()
"""
from .application_collector import ApplicationCollector
from .base import BaseCollector, ProbeReport
from .container_collector import ContainerCollector
from .database_collector import DatabaseCollector
from .log_collector import LogCollector
from .manager import ProbeManager
from .middleware_collector import MiddlewareCollector
from .network_collector import NetworkCollector
from .server_collector import ServerCollector

__all__ = [
    "BaseCollector", "ProbeReport", "ProbeManager",
    "ServerCollector", "ContainerCollector", "DatabaseCollector",
    "MiddlewareCollector", "ApplicationCollector", "NetworkCollector",
    "LogCollector",
]
