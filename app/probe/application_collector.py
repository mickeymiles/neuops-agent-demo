# -*- coding: utf-8 -*-
"""应用采集器：HTTP 健康探测 + 进程检测

覆盖：
- 9006 contract-compare 系统：HTTP 健康探测 + 进程/端口识别
- 9007 neuops 自身：HTTP 健康探测 + 进程识别
- 可扩展：从 settings 表 probe_apps 读取自定义应用（name|url|port|proc_kw）
"""
import os
import socket
import subprocess
import urllib.error
import urllib.request

from .base import BaseCollector, ProbeReport
from .. import config
from .. import db


class ApplicationCollector(BaseCollector):
    name = "application"
    label = "应用采集"
    entity_type = "application"

    def _http_health(self, url: str, timeout: float = 3.0) -> tuple:
        """返回 (ok, code_or_err, latency_ms)"""
        import time
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
            out = subprocess.run(["pgrep", "-f"], capture_output=True, text=True, timeout=5)
            # pgrep -f 需要参数，改用 ps 扫描
            out = subprocess.run(["ps", "-eo", "args"], capture_output=True,
                                 text=True, timeout=10)
            txt = out.stdout.lower()
            return any(kw.lower() in txt for kw in keywords)
        except Exception:  # noqa: BLE001
            return False

    def _collect_app(self, rpt: ProbeReport, host: str, name: str,
                     url: str, port: int, proc_kws: tuple, etype_suffix: str):
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
                       {"url": url, "port": port, "http_code": str(code)})
        rpt.add_metric("application", name, "health", 1 if ok_http else 0)
        rpt.add_metric("application", name, "latency_ms", latency, "ms")
        rpt.add_metric("application", name, "port_open", 1 if port_open else 0)
        rpt.add_relation(ent_id, f"server-{host}", "runs_on")

    def collect(self) -> ProbeReport:
        rpt = ProbeReport(collector=self.name)
        try:
            import socket as _s
            host = _s.gethostname()
        except Exception:
            host = "unknown"

        # 9006 contract-compare
        try:
            self._collect_app(
                rpt, host,
                config.APP_9006_NAME,
                config.APP_9006_BASE + config.APP_9006_HEALTH_PATH,
                9006,
                ("contract-compare", "9006"),
                "9006")
        except Exception as e:  # noqa: BLE001
            rpt.error = f"9006: {e}"

        # neuops 自身 9007
        try:
            self._collect_app(
                rpt, host,
                config.APP_NEUOPS_NAME,
                config.APP_NEUOPS_BASE + config.APP_NEUOPS_HEALTH_PATH,
                config.PORT,
                ("uvicorn", "neuops", str(config.PORT)),
                "self")
        except Exception as e:  # noqa: BLE001
            rpt.error = f"9007: {e}"

        # 自定义应用（settings 表 probe_apps: name|url|port|proc_kw, 逗号分隔）
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
                if url or port:
                    self._collect_app(rpt, host, name, url, port, proc_kws, "custom")
        except Exception:  # noqa: BLE001
            pass
        return rpt
