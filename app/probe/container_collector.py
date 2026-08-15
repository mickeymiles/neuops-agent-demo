# -*- coding: utf-8 -*-
"""容器采集器：真实 docker 命令采集容器状态与资源占用

无 docker 时返回失败但不断言系统错误（降级为无容器实体）。
"""
import json
import subprocess

from .base import BaseCollector, ProbeReport


class ContainerCollector(BaseCollector):
    name = "container"
    label = "容器采集"
    entity_type = "container"

    def _run(self, args, timeout=15):
        try:
            out = subprocess.run(["docker"] + args, capture_output=True,
                                 text=True, timeout=timeout)
            if out.returncode != 0:
                return None, out.stderr.strip()
            return out.stdout.strip(), None
        except FileNotFoundError:
            return None, "docker not installed"
        except subprocess.TimeoutExpired:
            return None, "docker timeout"
        except Exception as e:  # noqa: BLE001
            return None, str(e)

    def collect(self) -> ProbeReport:
        rpt = ProbeReport(collector=self.name)
        host = ""
        try:
            import socket
            host = socket.gethostname()
        except Exception:
            pass

        ps_out, err = self._run(["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.State}}", "--no-trunc"])
        if err:
            if "docker not installed" in err or "Cannot connect" in err:
                return ProbeReport(collector=self.name, ok=True,
                                   error="no docker daemon", collected_at=rpt.collected_at)
            return self.fail(f"container collect error: {err}")

        stats_out, stats_err = self._run(["stats", "--no-stream", "--format",
                                          "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"], timeout=20)
        stats_map = {}
        if stats_out and not stats_err:
            for line in stats_out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 4:
                    stats_map[parts[0]] = {"cpu": parts[1], "mem_usage": parts[2], "mem_perc": parts[3]}

        for line in ps_out.splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            cid, cname, image, status, state = parts[0], parts[1], parts[2], parts[3], parts[4]
            metrics = {}
            attrs = {"container_id": cid[:12], "image": image, "docker_status": status}
            if cname in stats_map:
                try:
                    metrics["cpu_percent"] = float(stats_map[cname]["cpu"].replace("%", ""))
                except ValueError:
                    pass
                try:
                    metrics["mem_percent"] = float(stats_map[cname]["mem_perc"].replace("%", ""))
                except ValueError:
                    pass
                mem_usage = stats_map[cname]["mem_usage"].split(" / ")[0]
                try:
                    if "GiB" in mem_usage:
                        metrics["mem_used_gb"] = float(mem_usage.replace("GiB", "").strip())
                    elif "MiB" in mem_usage:
                        metrics["mem_used_gb"] = float(mem_usage.replace("MiB", "").strip()) / 1024
                except ValueError:
                    pass
            ent_status = "running"
            if state == "exited" or state == "dead":
                ent_status = "down"
            elif state in ("restarting", "created"):
                ent_status = "degraded"
            rpt.add_entity(f"container-{cname}", "container", cname, ent_status, metrics, attrs)
            for k, v in metrics.items():
                rpt.add_metric("container", cname, k, v)
            if host:
                rpt.add_relation(f"container-{cname}", f"server-{host}", "runs_on")
        return rpt
