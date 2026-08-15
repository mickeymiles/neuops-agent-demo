# -*- coding: utf-8 -*-
"""探针管理器：统一调度全部采集器，聚合结果写入数据层

- run_once()  执行一轮全量采集（六类实体：服务器/容器/数据库/中间件/应用/网络）
- start()     后台线程按配置周期持续采集，超期数据按天清理
- stop()      停止后台采集
- cli 模式    支持独立进程运行并通过 HTTP 上报（远程探针预留）
"""
import json
import threading
from datetime import datetime

from .. import config, db
from .application_collector import ApplicationCollector
from .base import ProbeReport
from .container_collector import ContainerCollector
from .database_collector import DatabaseCollector
from .log_collector import LogCollector
from .middleware_collector import MiddlewareCollector
from .network_collector import NetworkCollector
from .server_collector import ServerCollector


class ProbeManager:
    """统一监控探针管理器"""

    def __init__(self, interval: int = None):
        self.interval = interval or config.OPS_PROBE_INTERVAL
        self.collectors = []
        self._thread = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self.last_run_at = ""
        self.last_reports = {}     # {collector_name: ProbeReport}
        self.last_error = ""
        # 确保运维表结构存在（应用内与独立 CLI 入口均可用）
        db.init_ops_db()
        self.register_defaults()

    # ---- 采集器注册 ----

    def register(self, collector):
        self.collectors.append(collector)
        return self

    def register_defaults(self):
        for cls in (ServerCollector, ContainerCollector, DatabaseCollector,
                    MiddlewareCollector, ApplicationCollector, NetworkCollector,
                    LogCollector):
            self.collectors.append(cls(probe=self))
        return self

    def collector_names(self) -> list:
        return [c.name for c in self.collectors]

    # ---- 采集执行 ----

    def run_once(self, ts: str = None) -> dict:
        """执行一轮全量采集并落库，返回 {collector_name: ok}"""
        ts = ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            summary = {}
            all_metrics, all_entities, all_relations, all_logs = [], [], [], []
            for col in self.collectors:
                try:
                    rpt = col.collect()
                except Exception as e:  # noqa: BLE001
                    rpt = ProbeReport(collector=col.name, ok=False, error=str(e))
                if not isinstance(rpt, ProbeReport):
                    rpt = ProbeReport(collector=col.name, ok=False, error="bad report")
                self.last_reports[col.name] = rpt
                summary[col.name] = rpt.ok
                if not rpt.ok:
                    self.last_error = f"{col.name}: {rpt.error}"
                    continue
                all_metrics.extend(rpt.metrics)
                all_entities.extend(rpt.entities)
                all_relations.extend(rpt.relations)
                all_logs.extend(rpt.logs)

            try:
                db.ops_save_metrics(ts, all_metrics)
                db.ops_save_entities(ts, all_entities)
                db.ops_save_relations(ts, all_relations)
                db.ops_save_logs([(ts, s, lv, msg) for s, lv, msg in all_logs])
            except Exception as e:  # noqa: BLE001
                self.last_error = f"persist error: {e}"

            self.last_run_at = ts
            return summary

    # ---- 后台线程 ----

    def _loop(self):
        # 先等待一个周期，给应用留启动时间
        if not self._stop_evt.wait(self.interval):
            self.run_once()
        while not self._stop_evt.wait(self.interval):
            self.run_once()
            # 按天清理超期数据（指标 + 日志）
            try:
                db.ops_cleanup_old_metrics(config.OPS_RETENTION_DAYS)
            except Exception:  # noqa: BLE001
                pass
            try:
                db.ops_cleanup_old_logs(config.OPS_RETENTION_DAYS)
            except Exception:  # noqa: BLE001
                pass

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, name="ops-probe", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self

    # ---- 上报/导出 ----

    def to_payload(self) -> dict:
        """本轮采集结果的可序列化负载（供独立 CLI 通过 HTTP 上报）"""
        payload = {
            "probe": "neuops-probe",
            "hostname": "",
            "interval": self.interval,
            "collected_at": self.last_run_at,
            "collectors": {},
        }
        try:
            import socket
            payload["hostname"] = socket.gethostname()
        except Exception:  # noqa: BLE001
            pass
        for name, rpt in self.last_reports.items():
            payload["collectors"][name] = {
                "ok": rpt.ok, "error": rpt.error,
                "metrics": rpt.metrics, "entities": rpt.entities,
                "relations": rpt.relations,
            }
        return payload

    def dump_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, indent=2)
