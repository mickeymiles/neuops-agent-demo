# -*- coding: utf-8 -*-
"""服务器采集器：psutil 真实采集 CPU / 内存 / 磁盘 / 负载 / 进程 / 网络IO"""
import socket
import time

from .base import BaseCollector, ProbeReport


class ServerCollector(BaseCollector):
    name = "server"
    label = "服务器采集"
    entity_type = "server"

    def __init__(self, probe=None):
        super().__init__(probe)
        self._prev_cpu = None
        self._prev_time = None

    def _hostname(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _cpu(self, rpt: ProbeReport, host: str):
        try:
            import psutil
        except ImportError:
            return
        # 两次采样间隔计算真实 CPU 使用率
        try:
            c = psutil.cpu_percent(interval=1)
        except Exception:
            c = 0.0
        rpt.add_metric(self.entity_type, host, "cpu_percent", c, "%")
        try:
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            rpt.add_metric(self.entity_type, host, "cpu_core_count", len(per_core), "core")
            rpt.add_metric(self.entity_type, host, "cpu_load_1m", psutil.getloadavg()[0], "")
            rpt.add_metric(self.entity_type, host, "cpu_load_5m", psutil.getloadavg()[1], "")
            rpt.add_metric(self.entity_type, host, "cpu_load_15m", psutil.getloadavg()[2], "")
        except Exception:
            pass

    def _memory(self, rpt: ProbeReport, host: str):
        try:
            import psutil
            vm = psutil.virtual_memory()
            rpt.add_metric(self.entity_type, host, "mem_total_gb", vm.total / 1024 ** 3, "GB")
            rpt.add_metric(self.entity_type, host, "mem_used_gb", vm.used / 1024 ** 3, "GB")
            rpt.add_metric(self.entity_type, host, "mem_available_gb", vm.available / 1024 ** 3, "GB")
            rpt.add_metric(self.entity_type, host, "mem_percent", vm.percent, "%")
            sm = psutil.swap_memory()
            rpt.add_metric(self.entity_type, host, "swap_percent", sm.percent, "%")
            rpt.add_metric(self.entity_type, host, "swap_total_gb", sm.total / 1024 ** 3, "GB")
        except Exception:
            pass

    def _disk(self, rpt: ProbeReport, host: str):
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    if part.fstype in ("", "squashfs", "tmpfs", "devtmpfs", "overlay"):
                        continue
                    usage = psutil.disk_usage(part.mountpoint)
                except (OSError, PermissionError):
                    continue
                safe = part.mountpoint.replace("/", "_").replace(".", "_").strip("_") or "root"
                ent = f"{host}-disk{safe}"
                rpt.add_entity(ent, "server", f"{host} [{part.mountpoint}]",
                               "running" if usage.percent < 90 else "degraded",
                               {"disk_percent": usage.percent, "disk_total_gb": round(usage.total / 1024 ** 3, 2),
                                "disk_used_gb": round(usage.used / 1024 ** 3, 2), "disk_free_gb": round(usage.free / 1024 ** 3, 2)},
                               {"mountpoint": part.mountpoint, "fstype": part.fstype, "device": part.device})
                rpt.add_metric(self.entity_type, host, f"disk_{safe}_percent", usage.percent, "%")
                rpt.add_metric(self.entity_type, host, f"disk_{safe}_used_gb", usage.used / 1024 ** 3, "GB")
                rpt.add_metric(self.entity_type, host, f"disk_{safe}_free_gb", usage.free / 1024 ** 3, "GB")
        except Exception:
            pass

    def _process_count(self, rpt: ProbeReport, host: str):
        try:
            import psutil
            procs = list(psutil.process_iter())
            running = sum(1 for p in procs if p.status() == psutil.STATUS_RUNNING)
            rpt.add_metric(self.entity_type, host, "process_count", len(procs), "")
            rpt.add_metric(self.entity_type, host, "process_running", running, "")
            # 内存/CPU 占用 Top5 进程
            top = sorted(procs,
                         key=lambda p: p.memory_percent() if p.memory_percent() is not None else 0,
                         reverse=True)[:5]
            attrs = {"top_processes": [{
                "pid": p.pid, "name": p.name(),
                "cpu": round(p.cpu_percent(interval=None) or 0, 1),
                "mem": round(p.memory_percent() or 0, 1),
            } for p in top]}
            return attrs
        except Exception:
            return {}

    def _uptime(self, rpt: ProbeReport, host: str):
        try:
            import psutil
            boot = psutil.boot_time()
            uptime = int(time.time() - boot)
            rpt.add_metric(self.entity_type, host, "uptime_sec", uptime, "s")
            days = uptime // 86400
            rpt.add_entity(f"uptime-{host}", "server", f"{host}-uptime", "running",
                           {"uptime_days": days, "boot_ts": int(boot)},
                           {})
        except Exception:
            pass

    def collect(self) -> ProbeReport:
        host = self._hostname()
        rpt = ProbeReport(collector=self.name)
        try:
            self._cpu(rpt, host)
            self._memory(rpt, host)
            self._disk(rpt, host)
            top_attrs = self._process_count(rpt, host)
            self._uptime(rpt, host)

            attrs = {"hostname": host, "platform": "", "python": ""}
            try:
                import platform
                attrs["platform"] = platform.platform()
                attrs["python"] = platform.python_version()
            except Exception:
                pass
            attrs.update(top_attrs)
            status = "running"
            for (_, _, metric, value, _) in rpt.metrics:
                if metric == "cpu_percent" and value >= 90:
                    status = "degraded"
                if metric == "mem_percent" and value >= 90:
                    status = "degraded"
            rpt.add_entity(f"server-{host}", "server", host, status, {}, attrs)
            rpt.add_relation(f"server-{host}", f"server-{host}", "self")
        except Exception as e:  # noqa: BLE001
            return self.fail(f"server collect error: {e}")
        return rpt
