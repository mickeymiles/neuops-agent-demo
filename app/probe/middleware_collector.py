# -*- coding: utf-8 -*-
"""中间件采集器：端口探测 + 进程识别

对配置中的中间件候选（Redis/MySQL/PG/Nginx/RabbitMQ/Kafka/ES/MongoDB）：
- socket 探测端口连通性
- 进程名/命令匹配确认实例
- 命中才登记为本体实体（middleware）
"""
import socket
import subprocess

from .base import BaseCollector, ProbeReport
from .. import config

# 进程识别关键词 -> 中间件
PROC_KEYWORDS = {
    "redis": ("redis-server",),
    "mysql": ("mysqld",),
    "postgresql": ("postgres",),
    "nginx": ("nginx",),
    "rabbitmq": ("beam.smp", "rabbitmq"),
    "kafka": ("kafka.Kafka",),
    "elasticsearch": ("elasticsearch",),
    "mongodb": ("mongod",),
}


class MiddlewareCollector(BaseCollector):
    name = "middleware"
    label = "中间件采集"
    entity_type = "middleware"

    def _port_open(self, port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _running_procs(self) -> list:
        """真实进程命令行列表，用于中间件实例识别"""
        procs = []
        try:
            out = subprocess.run(["ps", "-eo", "comm,args"], capture_output=True,
                                 text=True, timeout=10)
            if out.returncode == 0:
                for line in out.stdout.splitlines():
                    line = line.strip()
                    if line:
                        procs.append(line)
        except Exception:  # noqa: BLE001
            pass
        return procs

    def collect(self) -> ProbeReport:
        rpt = ProbeReport(collector=self.name)
        try:
            import socket as _s
            host = _s.gethostname()
        except Exception:
            host = "unknown"
        procs = self._running_procs()
        proc_txt = "\n".join(procs).lower()

        for item in config.MIDDLEWARE_PROBES:
            name, label = item["name"], item["label"]
            ports = item["ports"]
            open_ports = [p for p in ports if self._port_open(p)]
            proc_hit = any(kw in proc_txt for kw in PROC_KEYWORDS.get(name, ()))
            if not open_ports and not proc_hit:
                continue  # 未命中，不登记实体
            status = "running"
            if open_ports and proc_hit:
                status = "running"
            elif open_ports and not proc_hit:
                status = "degraded"  # 端口通但进程不确定
            else:
                status = "down"  # 进程在但端口不通
            ent_id = f"middleware-{name}"
            rpt.add_entity(ent_id, "middleware", name, status,
                           {"health": 1 if status == "running" else 0,
                            "port_open": 1 if open_ports else 0},
                           {"label": label, "ports": list(ports),
                            "open_ports": open_ports, "proc_detected": proc_hit})
            rpt.add_metric("middleware", name, "health", 1 if status == "running" else 0)
            rpt.add_metric("middleware", name, "port_open", 1 if open_ports else 0)
            for p in open_ports:
                rpt.add_metric("middleware", name, f"port_{p}", 1)
            rpt.add_relation(ent_id, f"server-{host}", "runs_on")
        return rpt
