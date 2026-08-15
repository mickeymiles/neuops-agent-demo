# -*- coding: utf-8 -*-
"""MCP 工具层：请求模型 + 6 个 Mock MCP 工具"""
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel

from .mock_data import MOCK_METRICS, MOCK_LOGS, MOCK_CMDB, MOCK_CHANGES, MOCK_ALARMS


class ChatRequest(BaseModel):
    query: str
    conversation_id: str = ""
    mode: str = "free"       # "free" | "skill"
    selected_skill: str = "" # skill id when mode=skill
    enabled_skills: list = []
    approved_action: Optional[str] = None  # 审批确认后携带

# ────────────────────────────────────────────
# Mock MCP Tool Handlers
# ────────────────────────────────────────────

def tool_get_business_metric(service: str = "order-service", metric: str = "all") -> dict:
    data = MOCK_METRICS.get(service, MOCK_METRICS["order-service"])
    timestamps = [(datetime.now() - timedelta(minutes=5*i)).strftime("%H:%M") for i in range(7, 0, -1)]
    return {
        "tool": "get_business_metric",
        "service": service,
        "metric": metric,
        "data": {
            "timestamps": timestamps,
            "metrics": data,
            "summary": f"{service} P99延迟从 {data['latency_p99'][0]}ms 上升至 {data['latency_p99'][-1]}ms，增幅 {round((data['latency_p99'][-1]/data['latency_p99'][0]-1)*100)}%；错误率从 {data['error_rate'][0]}% 升至 {data['error_rate'][-1]}%"
        }
    }

def tool_search_service_log(service: str = "order-service", level: str = "ERROR") -> dict:
    logs = [l for l in MOCK_LOGS if l["service"] == service and (level == "ALL" or l["level"] == level)]
    return {
        "tool": "search_service_log",
        "service": service,
        "level": level,
        "total": len(logs),
        "logs": logs,
    }

def tool_query_cmdb_topology(app: str = "order-service") -> dict:
    """优先返回真实运维本体数据；真实数据不足时回退到 MOCK_CMDB 兜底"""
    from . import ops_ontology
    topo = ops_ontology.build_topology()
    nodes = topo.get("nodes", [])
    # 若本体无数据，则回退到旧 mock 数据保持兼容性
    if not nodes:
        data = MOCK_CMDB.get(app, MOCK_CMDB["order-service"])
        return {"tool": "query_cmdb_topology", "app": app, "data": data, "source": "mock"}
    # 尝试按应用名过滤子图
    app_nodes = [n for n in nodes if app.lower() in n.get("name", "").lower()]
    if not app_nodes:
        app_nodes = nodes
    ids = {n["id"] for n in app_nodes}
    edges = [e for e in topo.get("edges", []) if e["source"] in ids or e["target"] in ids]
    return {
        "tool": "query_cmdb_topology",
        "app": app,
        "data": {
            "nodes": app_nodes,
            "edges": edges,
            "summary": topo.get("summary", {}),
        },
        "source": "real",
    }

def tool_query_change_record(service: str = "order-service", hours: int = 24) -> dict:
    cutoff = datetime.now() - timedelta(hours=hours)
    changes = MOCK_CHANGES  # all recent enough for demo
    return {
        "tool": "query_change_record",
        "service": service,
        "hours": hours,
        "total": len(changes),
        "changes": changes,
    }

def tool_run_auto_job(job_type: str, target: str) -> dict:
    return {
        "tool": "run_auto_job",
        "job_type": job_type,
        "target": target,
        "status": "success",
        "message": f"自动化作业执行成功：{job_type} → {target}",
        "execution_id": f"JOB-{uuid.uuid4().hex[:8].upper()}",
        "duration": f"{random.uniform(2.5, 8.0):.1f}s",
    }

def tool_query_alarm_info(service: str = "order-service") -> dict:
    alarms = [a for a in MOCK_ALARMS if a["service"] == service]
    return {
        "tool": "query_alarm_info",
        "service": service,
        "total": len(alarms),
        "alarms": alarms,
    }
