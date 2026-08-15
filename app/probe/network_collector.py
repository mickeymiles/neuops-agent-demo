# -*- coding: utf-8 -*-
"""网络采集器：网卡流量 / 连接统计 / 端口监听

- psutil.net_io_counters(pernic=True) 采集各网卡实时流量（采样差值）
- psutil.net_connections 统计 LISTEN / ESTABLISHED 连接数
- 采样两次计算速率（B/s）
"""
import time

from .base import BaseCollector, ProbeReport

_PREV_IO = {}


class NetworkCollector(BaseCollector):
    name = "network"
    label = "网络采集"
    entity_type = "network"

    def collect(self) -> ProbeReport:
        global _PREV_IO
        rpt = ProbeReport(collector=self.name)
        try:
            import socket as _s
            host = _s.gethostname()
        except Exception:
            host = "unknown"
        try:
            import psutil
        except ImportError:
            return self.fail("psutil not installed")

        now = time.time()
        try:
            io = psutil.net_io_counters(pernic=True)
        except Exception as e:  # noqa: BLE001
            return self.fail(f"network collect error: {e}")

        # 连接统计：psutil 可能因权限不足抛 AccessDenied（macOS 常见），降级用 lsof
        listen_cnt = established_cnt = 0
        conns = []
        try:
            conns = psutil.net_connections(kind="all")
            listen_cnt = sum(1 for c in conns if c.status == "LISTEN")
            established_cnt = sum(1 for c in conns if c.status == "ESTABLISHED")
        except (psutil.AccessDenied, PermissionError, OSError):
            try:
                import subprocess
                out = subprocess.run(
                    ["lsof", "-iTCP", "-P", "-n"],
                    capture_output=True, text=True, timeout=10)
                for line in out.stdout.splitlines()[1:]:
                    if "(LISTEN)" in line:
                        listen_cnt += 1
                    elif "(ESTABLISHED)" in line:
                        established_cnt += 1
            except Exception:  # noqa: BLE001
                pass
        rpt.add_metric("network", "all", "listen_ports", listen_cnt)
        rpt.add_metric("network", "all", "established_conns", established_cnt)
        rpt.add_entity("network-all", "network", "all-connections", "running",
                       {"listen_ports": listen_cnt, "established_conns": established_cnt,
                        "total_conns": len(conns)},
                       {"status": "listening"})
        rpt.add_relation("network-all", f"server-{host}", "hosted_on")

        # 网卡速率（两次采样）
        total_sent = total_recv = 0
        for nic, c in io.items():
            if c.bytes_sent == 0 and c.bytes_recv == 0:
                continue
            key = f"nic-{nic}"
            prev = _PREV_IO.get(key)
            delta = now - prev[0] if prev else 0
            if prev and delta > 0:
                sent_rate = max((c.bytes_sent - prev[1]) / delta, 0)
                recv_rate = max((c.bytes_recv - prev[2]) / delta, 0)
                total_sent += sent_rate
                total_recv += recv_rate
                rpt.add_metric("network", nic, "tx_rate_bps", round(sent_rate), "B/s")
                rpt.add_metric("network", nic, "rx_rate_bps", round(recv_rate), "B/s")
                rpt.add_metric("network", nic, "bytes_sent_total", c.bytes_sent)
                rpt.add_metric("network", nic, "bytes_recv_total", c.bytes_recv)
                rpt.add_entity(f"network-{nic}", "network", nic, "running",
                               {"tx_rate_bps": round(sent_rate), "rx_rate_bps": round(recv_rate)},
                               {"family": "nic"})
                rpt.add_relation(f"network-{nic}", f"server-{host}", "hosted_on")
            _PREV_IO[key] = (now, c.bytes_sent, c.bytes_recv)

        rpt.add_metric("network", "all", "tx_total_bps", round(total_sent), "B/s")
        rpt.add_metric("network", "all", "rx_total_bps", round(total_recv), "B/s")
        return rpt
