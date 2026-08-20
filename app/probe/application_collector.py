# -*- coding: utf-8 -*-
"""应用采集器：通用型应用发现 + HTTP 健康探测

通用探测原则（有什么就监视什么，不绑定任何特定主机/服务）：
1. 动态发现本机所有监听端口（lsof / psutil 双通道），对每个端口做 HTTP 探测，
   可访问则登记为 application 实体；本机没有的服务一律不登记。
2. 应用名识别：已知端口映射（config.APP_PORT_HINTS，如 9006→contract-compare）
   → 监听进程名 → app-{port}。
3. 明确的中间件/数据库协议端口（MySQL/PG/Redis/ES/Mongo/Kafka/RabbitMQ 等）
   由 middleware / database 采集器负责，此处跳过，避免重复实体。
4. settings 表 probe_apps 可自定义补充应用（name|url|port|proc_kw, 逗号分隔），
   用于显式监视本机之外的 URL 或补充识别规则。
"""
import re
import socket
import subprocess
import urllib.error
import urllib.request

from .. import config, db
from .base import BaseCollector, ProbeReport

# 明确由中间件/数据库采集器负责的协议端口，应用采集跳过（避免无谓 HTTP 探测与重复实体）
SKIP_PORTS = {
    22,        # ssh
    2375,      # docker
    3306,      # mysql
    5432,      # postgres
    6379,      # redis
    9200,      # elasticsearch
    11211,     # memcached
    27017,     # mongodb
    5672,      # rabbitmq
    15672,     # rabbitmq mgmt
    9092,      # kafka
}

# 已知端口 → 应用名提示（仅当该端口在本机被监听到时生效）
PORT_NAME_HINTS = dict(getattr(config, "APP_PORT_HINTS", {}) or {})


class ApplicationCollector(BaseCollector):
    name = "application"
    label = "应用采集"
    entity_type = "application"

    def _http_health(self, url: str, timeout: float = 2.0) -> tuple:
        """返回 (ok, code_or_err, latency_ms)"""
        import time
        if not url:
            return False, "no url", 0.0
        start = time.time()
        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "neuops-probe"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                latency = (time.time() - start) * 1000
                return resp.status < 500, resp.status, round(latency, 1)
        except urllib.error.HTTPError as e:
            latency = (time.time() - start) * 1000
            return e.code < 500, e.code, round(latency, 1)
        except Exception as e:  # noqa: BLE001
            return False, str(e), 0.0

    def _port_open(self, port: int, timeout: float = 0.5) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                return True
        except OSError:
            return False

    def _proc_detect(self, keywords) -> bool:
        try:
            out = subprocess.run(["ps", "-eo", "args"], capture_output=True,
                                 text=True, timeout=10)
            txt = out.stdout.lower()
            return any(kw.lower() in txt for kw in keywords)
        except Exception:  # noqa: BLE001
            return False

    def _discover_listen_ports(self) -> dict:
        """返回 {port: [进程名,...]} —— 本机所有监听端口及对应进程（lsof / psutil 双通道）"""
        ports = {}
        # 通道1: lsof（Linux/macOS 通用；权限不足时可能失败）
        try:
            out = subprocess.run(
                ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
                capture_output=True, text=True, timeout=10)
            if out.returncode == 0:
                for line in out.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    # NAME 列形如 `TCP *:9007 (LISTEN)`（IPv6 为 `[::]:9007`），
                    # 端口从整行提取，进程名取 COMMAND 列（parts[0]）
                    m = re.search(r":(\d+)\s*(?:\(LISTEN\))?\s*$", line)
                    if not m:
                        continue
                    port = int(m.group(1))
                    cmd = parts[0]
                    if port not in ports:
                        ports[port] = []
                    if cmd and cmd not in ports[port]:
                        ports[port].append(cmd)
        except Exception:  # noqa: BLE001
            pass
        # 通道2: psutil 兜底
        if not ports:
            try:
                import psutil
                for c in psutil.net_connections(kind="listener"):
                    if not c.laddr or not c.laddr.port:
                        continue
                    port = c.laddr.port
                    if port not in ports:
                        ports[port] = []
                    try:
                        pname = psutil.Process(c.pid).name()
                        if pname and pname not in ports[port]:
                            ports[port].append(pname)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
        return ports

    def _collect_app(self, rpt: ProbeReport, host: str, name: str,
                     url: str, port: int, proc_kws: tuple, source: str):
        ok_http, code, latency = self._http_health(url)
        port_open = self._port_open(port) if port else False
        proc_ok = self._proc_detect(proc_kws) if proc_kws else False
        status = "running"
        if ok_http and (port_open or proc_ok):
            status = "running"
        elif ok_http or port_open or proc_ok:
            status = "degraded"
        else:
            status = "down"
        ent_id = f"application-{name}"
        rpt.add_entity(ent_id, "application", name, status,
                       {"health": 1 if ok_http else 0, "latency_ms": latency,
                        "port_open": 1 if port_open else 0,
                        "proc_running": 1 if proc_ok else 0},
                       {"url": url, "port": port, "http_code": str(code),
                        "source": source,
                        "proc": ",".join(proc_kws) if proc_kws else ""})
        rpt.add_metric("application", name, "health", 1 if ok_http else 0)
        rpt.add_metric("application", name, "latency_ms", latency, "ms")
        rpt.add_metric("application", name, "port_open", 1 if port_open else 0)
        rpt.add_relation(ent_id, f"server-{host}", "runs_on")

    def collect(self) -> ProbeReport:
        rpt = ProbeReport(collector=self.name)
        try:
            import socket as _s
            host = _s.gethostname()
        except Exception:  # noqa: BLE001
            host = "unknown"

        # 1) 通用发现：本机监听端口 → HTTP 探测 → 有什么就登记什么
        try:
            listen = self._discover_listen_ports()
            seen = set()
            for port, procs in sorted(listen.items()):
                if port in SKIP_PORTS:
                    continue
                ok_http, code, latency = self._http_health(
                    f"http://127.0.0.1:{port}/")
                if not ok_http:
                    # 非 HTTP 服务（中间件/数据库等）由对应采集器负责
                    continue
                name = PORT_NAME_HINTS.get(port) or (procs[0] if procs else "")
                if not name:
                    name = f"app-{port}"
                if name in seen:
                    name = f"{name}-{port}"
                seen.add(name)
                self._collect_app(rpt, host, name,
                                  f"http://127.0.0.1:{port}/", port,
                                  tuple(procs), "discovered")
        except Exception as e:  # noqa: BLE001
            rpt.error = f"discover: {e}"

        # 2) 自定义应用（settings 表 probe_apps: name|url|port|proc_kw, 逗号分隔）
        try:
            custom = db.db_get_setting("probe_apps", "")
            for line in custom.replace(";", "\n").splitlines():
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                name = parts[0]
                url = parts[1] if len(parts) > 1 else ""
                port = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                proc_kws = tuple(parts[3].split(",")) if len(parts) > 3 and parts[3] else ()
                if not url and port:
                    url = f"http://127.0.0.1:{port}/"
                if url or port:
                    self._collect_app(rpt, host, name, url, port, proc_kws, "custom")
        except Exception:  # noqa: BLE001
            pass
        return rpt
