# -*- coding: utf-8 -*-
"""探针基类与统一采集结果格式

所有采集器继承 BaseCollector，实现 collect() 返回 ProbeReport。
ProbeReport 是六类实体采集的统一载体：
    metrics   时序指标（写入 ops_metrics）
    entities  本体实体状态（写入 ops_entities）
    relations 本体关系（写入 ops_relations）
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProbeReport:
    """一次采集的统一结果"""
    collector: str                # 采集器名
    ok: bool = True               # 本次采集是否成功
    error: str = ""               # 失败原因
    metrics: list = field(default_factory=list)      # [(entity_type, entity_name, metric, value, unit)]
    entities: list = field(default_factory=list)     # [dict(id,type,name,status,metrics,attrs)]
    relations: list = field(default_factory=list)    # [(source, target, type)]
    logs: list = field(default_factory=list)         # [(source, level, message)] 统一日志采集
    collected_at: str = ""        # 采集时间 ISO

    def __post_init__(self):
        if not self.collected_at:
            self.collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def add_metric(self, entity_type: str, entity_name: str,
                   metric: str, value, unit: str = ""):
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = 0.0
        self.metrics.append((entity_type, entity_name, metric, v, unit))

    def add_entity(self, entity_id: str, etype: str, name: str, status: str,
                   metrics: dict = None, attrs: dict = None):
        self.entities.append({
            "id": entity_id, "type": etype, "name": name, "status": status,
            "metrics": metrics or {}, "attrs": attrs or {},
        })

    def add_relation(self, source: str, target: str, rtype: str):
        self.relations.append((source, target, rtype))

    def add_log(self, source: str, level: str, message: str):
        self.logs.append((source, (level or "info").lower(), message))


class BaseCollector(ABC):
    """采集器基类。子类必须定义 name/label/entity_type 并实现 collect()。"""

    name = "base"          # 采集器标识（唯一）
    label = "基础采集器"    # 展示名
    entity_type = ""       # 对应本体实体类型：server/database/network/container/middleware/application

    def __init__(self, probe=None):
        self.probe = probe  # 反向引用探针管理器（可选，用于读取配置/共享状态）

    @abstractmethod
    def collect(self) -> ProbeReport:
        """执行一次真实采集，返回统一结果"""
        raise NotImplementedError

    def fail(self, error: str) -> ProbeReport:
        return ProbeReport(collector=self.name, ok=False, error=error)
