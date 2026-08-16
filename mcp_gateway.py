"""
MCP 工具网关 — 统一原子工具服务
端口: 9010
数据源: 环境变量 DATA_SOURCE=mock|real (默认 mock)

架构:
  Dify Cloud (Workflow HTTP节点)
      │
      ▼
  本网关 (9010) ──DATA_SOURCE=mock──→ mock_data.py
      │
      └──DATA_SOURCE=real──→ 真实运维系统 API
"""
import os
import json
import httpx
from datetime import datetime, timedelta
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from mock_data import (
    MOCK_METRICS, MOCK_LOGS, MOCK_CMDB,
    MOCK_CHANGES, MOCK_ALARMS, MOCK_TODOS,
    get_timestamps,
)

# ────────────────────────────────────────────
# 数据源切换
# ────────────────────────────────────────────
DATA_SOURCE = os.getenv("DATA_SOURCE", "mock").lower()
print(f"[MCP Gateway] 数据源: {DATA_SOURCE}")

# 经营业务数据源（9006 经营分析系统：原子本体 MCP + 指标数据集 MCP）
BIZ_9006_BASE = os.getenv("BIZ_9006_BASE", "http://127.0.0.1:9006")

# 运维监控数据源（9007 一体化监控平台：实体/指标/日志/告警/事件 + AI 自监控）
NEUOPS_BASE = os.getenv("NEUOPS_BASE", "http://127.0.0.1:9007")

app = FastAPI(title="NeuOps MCP Tool Gateway", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ═══════════════════════════════════════════
# 统一工具响应格式
# ═══════════════════════════════════════════

def tool_response(tool_name: str, success: bool, data: dict, **extra) -> dict:
    # source 参数用于标记真实数据源（9006/9007），优先于全局 DATA_SOURCE
    ds = extra.pop("source", DATA_SOURCE)
    return {
        "tool": tool_name,
        "success": success,
        "timestamp": datetime.now().isoformat(),
        "data_source": ds,
        "data": data,
        **extra,
    }


# ═══════════════════════════════════════════
# 工具: 查询业务指标
# ═══════════════════════════════════════════

@app.post("/tools/get_business_metric")
@app.get("/tools/get_business_metric")
async def get_business_metric(
    service: str = Query(default="order-service"),
    metric: str = Query(default="all"),
):
    if DATA_SOURCE == "real":
        return await _real_get_business_metric(service, metric)

    # Mock
    data = MOCK_METRICS.get(service, MOCK_METRICS["order-service"])
    ts = get_timestamps(7)
    return tool_response("get_business_metric", True, {
        "service": service,
        "metric": metric,
        "timestamps": ts,
        "metrics": data,
        "summary": f"{service} P99延迟 {data['latency_p99'][0]}→{data['latency_p99'][-1]}ms, "
                   f"错误率 {data['error_rate'][0]}%→{data['error_rate'][-1]}%"
    })


# ═══════════════════════════════════════════
# 工具: 检索服务日志
# ═══════════════════════════════════════════

@app.post("/tools/search_service_log")
@app.get("/tools/search_service_log")
async def search_service_log(
    service: str = Query(default="order-service"),
    level: str = Query(default="ERROR"),
    limit: int = Query(default=50),
):
    if DATA_SOURCE == "real":
        return await _real_search_service_log(service, level, limit)

    logs = [l for l in MOCK_LOGS
            if l["service"] == service and (level == "ALL" or l["level"] == level)]
    return tool_response("search_service_log", True, {
        "service": service,
        "level": level,
        "total": len(logs),
        "logs": logs[:limit],
    })


# ═══════════════════════════════════════════
# 工具: 查询 CMDB 资产拓扑
# ═══════════════════════════════════════════

@app.post("/tools/query_cmdb_topology")
@app.get("/tools/query_cmdb_topology")
async def query_cmdb_topology(
    app: str = Query(default="order-service"),
):
    if DATA_SOURCE == "real":
        return await _real_query_cmdb_topology(app)

    data = MOCK_CMDB.get(app, MOCK_CMDB["order-service"])
    return tool_response("query_cmdb_topology", True, {"app": app, "topology": data})


# ═══════════════════════════════════════════
# 工具: 查询变更记录
# ═══════════════════════════════════════════

@app.post("/tools/query_change_record")
@app.get("/tools/query_change_record")
async def query_change_record(
    service: str = Query(default="order-service"),
    hours: int = Query(default=24),
):
    if DATA_SOURCE == "real":
        return await _real_query_change_record(service, hours)

    return tool_response("query_change_record", True, {
        "service": service,
        "hours": hours,
        "total": len(MOCK_CHANGES),
        "changes": MOCK_CHANGES,
    })


# ═══════════════════════════════════════════
# 工具: 查询告警信息
# ═══════════════════════════════════════════

@app.post("/tools/query_alarm_info")
@app.get("/tools/query_alarm_info")
async def query_alarm_info(
    service: str = Query(default="order-service"),
):
    if DATA_SOURCE == "real":
        return await _real_query_alarm_info(service)

    alarms = [a for a in MOCK_ALARMS if a["service"] == service]
    return tool_response("query_alarm_info", True, {
        "service": service,
        "total": len(alarms),
        "alarms": alarms,
    })


# ═══════════════════════════════════════════
# 工具: 执行自动化作业
# ═══════════════════════════════════════════

@app.post("/tools/run_auto_job")
@app.get("/tools/run_auto_job")
async def run_auto_job(
    job_type: str = Query(default="restart"),
    target: str = Query(default="order-service"),
):
    if DATA_SOURCE == "real":
        return await _real_run_auto_job(job_type, target)

    import uuid, random
    return tool_response("run_auto_job", True, {
        "job_type": job_type,
        "target": target,
        "status": "success",
        "message": f"自动化作业执行成功：{job_type} → {target}",
        "execution_id": f"JOB-{uuid.uuid4().hex[:8].upper()}",
        "duration": f"{random.uniform(2.5, 8.0):.1f}s",
    })


# ═══════════════════════════════════════════
# 工具: 变更风险预检查
# ═══════════════════════════════════════════

@app.post("/tools/query_change_risk")
@app.get("/tools/query_change_risk")
async def query_change_risk(
    service: str = Query(default="order-service"),
    change: str = Query(default=""),
):
    if DATA_SOURCE == "real":
        return tool_response("query_change_risk", False, {"error": "真实数据源未配置"})
    risk_level = "低"
    if "restart" in change or "重启" in change:
        risk_level = "中"
    return tool_response("query_change_risk", True, {
        "service": service,
        "change": change,
        "risk_level": risk_level,
        "affected_assets": 3,
        "suggestion": "变更影响范围可控，建议灰度发布并回滚预案。",
    })


# ═══════════════════════════════════════════
# 工具: 变更后业务验证
# ═══════════════════════════════════════════

@app.post("/tools/verify_service_status")
@app.get("/tools/verify_service_status")
async def verify_service_status(
    service: str = Query(default="order-service"),
):
    if DATA_SOURCE == "real":
        return tool_response("verify_service_status", False, {"error": "真实数据源未配置"})
    return tool_response("verify_service_status", True, {
        "service": service,
        "status": "healthy",
        "http_ok": True,
        "latency_p99_ms": 120,
        "error_rate": 0.01,
        "message": "服务健康，变更验证通过。",
    })


# ═══════════════════════════════════════════
# 工具: 检索慢查询日志
# ═══════════════════════════════════════════

@app.post("/tools/search_slow_query")
@app.get("/tools/search_slow_query")
async def search_slow_query(
    instance: str = Query(default="order-db"),
    hours: int = Query(default=24),
):
    if DATA_SOURCE == "real":
        return tool_response("search_slow_query", False, {"error": "真实数据源未配置"})
    return tool_response("search_slow_query", True, {
        "instance": instance,
        "hours": hours,
        "total": 2,
        "slow_queries": [
            {"sql": "SELECT * FROM orders WHERE status=?", "exec_ms": 3200,
             "hits": 120, "suggestion": "缺少 status 索引"},
            {"sql": "SELECT * FROM contract_items JOIN contract ON ...", "exec_ms": 2100,
             "hits": 80, "suggestion": "大表 JOIN 建议物化视图"},
        ],
    })


# ═══════════════════════════════════════════
# 工具: 查询容器资源画像
# ═══════════════════════════════════════════

@app.post("/tools/query_container_resource")
@app.get("/tools/query_container_resource")
async def query_container_resource(
    app: str = Query(default="order-service"),
):
    if DATA_SOURCE == "real":
        return tool_response("query_container_resource", False, {"error": "真实数据源未配置"})
    return tool_response("query_container_resource", True, {
        "app": app,
        "pods": 6,
        "cpu_usage_pct": 62,
        "memory_usage_pct": 71,
        "bottleneck": "内存",
        "suggestion": "建议扩容至 8 副本或调大内存配额。",
    })


# ═══════════════════════════════════════════
# 工具: 安全漏洞扫描
# ═══════════════════════════════════════════

@app.post("/tools/scan_vulnerability")
@app.get("/tools/scan_vulnerability")
async def scan_vulnerability(
    service: str = Query(default="order-service"),
):
    if DATA_SOURCE == "real":
        return tool_response("scan_vulnerability", False, {"error": "真实数据源未配置"})
    return tool_response("scan_vulnerability", True, {
        "service": service,
        "total": 1,
        "high": 0,
        "medium": 1,
        "low": 0,
        "vulnerabilities": [
            {"cve": "CVE-2024-0001", "level": "medium",
             "desc": "日志组件存在中等风险漏洞，建议升级版本。"},
        ],
    })


# ═══════════════════════════════════════════
# 经营业务：原子本体 MCP（原始表查询，转发 9006）
# ═══════════════════════════════════════════

@app.post("/tools/query_ontology")
@app.get("/tools/query_ontology")
async def query_ontology(
    table_name: str = Query(default="总合同表"),
    keyword: str = Query(default=""),
    limit: int = Query(default=50),
):
    """查询原始明细（原子本体 MCP，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/query",
                                 params={"table_name": table_name, "keyword": keyword, "limit": limit})
            data = r.json()
    except Exception as e:
        return tool_response("query_ontology", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("query_ontology", True, data,
                         source="9006", table_name=table_name, keyword=keyword)


@app.post("/tools/query_ontology_tables")
@app.get("/tools/query_ontology_tables")
async def query_ontology_tables():
    """列出原始本体表（原子本体 MCP，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/tables")
            data = r.json()
    except Exception as e:
        return tool_response("query_ontology_tables", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("query_ontology_tables", True, data, source="9006")


# ═══════════════════════════════════════════
# 经营业务：指标数据集 MCP（宽表查询，转发 9006）
# ═══════════════════════════════════════════

@app.post("/tools/get_etl_metrics")
@app.get("/tools/get_etl_metrics")
async def get_etl_metrics(
    job_key: str = Query(default=""),
    metric_name: str = Query(default=""),
    dim_type: str = Query(default=""),
):
    """查询指标汇总宽表（指标数据集 MCP，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/etl/metrics",
                                 params={"job_key": job_key, "metric_name": metric_name, "dim_type": dim_type})
            data = r.json()
    except Exception as e:
        return tool_response("get_etl_metrics", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("get_etl_metrics", True, data,
                         source="9006", job_key=job_key, dim_type=dim_type)


@app.post("/tools/get_table_schema")
@app.get("/tools/get_table_schema")
async def get_table_schema(
    table_name: str = Query(default="总合同表"),
):
    """获取表结构（原子本体 MCP，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/schema",
                                 params={"table_name": table_name})
            data = r.json()
    except Exception as e:
        return tool_response("get_table_schema", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("get_table_schema", True, data,
                         source="9006", table_name=table_name)


# ═══════════════════════════════════════════
# 经营业务：合同比对引擎（转发 9006）
# ═══════════════════════════════════════════

@app.post("/tools/query_contracts")
@app.get("/tools/query_contracts")
async def query_contracts():
    """获取全部合同及比对进度概览（合同比对引擎，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/contracts")
            data = r.json()
    except Exception as e:
        return tool_response("query_contracts", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("query_contracts", True, data, source="9006")


@app.post("/tools/get_contract_stats")
@app.get("/tools/get_contract_stats")
async def get_contract_stats(
    cid: str = Query(default=""),
):
    """获取指定合同的比对统计汇总（合同比对引擎，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/contract/{cid}/stats")
            data = r.json()
    except Exception as e:
        return tool_response("get_contract_stats", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("get_contract_stats", True, data,
                         source="9006", cid=cid)


@app.post("/tools/get_comparison_results")
@app.get("/tools/get_comparison_results")
async def get_comparison_results(
    cid: str = Query(default=""),
):
    """获取指定合同逐项比对明细（合同比对引擎，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/contract/{cid}/compare/results")
            data = r.json()
    except Exception as e:
        return tool_response("get_comparison_results", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("get_comparison_results", True, data,
                         source="9006", cid=cid)


@app.post("/tools/export_report")
@app.get("/tools/export_report")
async def export_report(
    cid: str = Query(default=""),
):
    """导出合同比对报告 Excel（合同比对引擎，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/contract/{cid}/compare/export")
            data = r.json()
    except Exception as e:
        return tool_response("export_report", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("export_report", True, data,
                         source="9006", cid=cid)


# ═══════════════════════════════════════════
# 运维域：9007 一体化监控平台（只读，转发 9007 真实数据）
#   - 基础设施巡检：实体/指标/拓扑
#   - 告警与事件：告警聚合/事件/规则
#   - 日志检索：统一日志查询
#   - AI 自监控：智能体状态/时序/长任务
# ═══════════════════════════════════════════

async def _neuops_forward(tool_name: str, path: str, params: dict = None) -> dict:
    """统一转发 9007 一体化监控平台（全部只读）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{NEUOPS_BASE}{path}", params=params or {})
            data = r.json()
    except Exception as e:
        return tool_response(tool_name, False,
                             {"error": f"无法连接9007一体化监控平台: {e}"})
    return tool_response(tool_name, True, data, source="9007")


@app.post("/tools/ops_overview")
@app.get("/tools/ops_overview")
async def ops_overview():
    """获取运维全域概览（实体/指标/告警/事件统计，只读，转发 9007）"""
    return await _neuops_forward("ops_overview", "/api/ops/overview")


@app.post("/tools/ops_entities")
@app.get("/tools/ops_entities")
async def ops_entities(type: str = Query(default="", description="实体类型：server/database/network/container/middleware/application")):
    """查询运维实体清单（服务器/数据库/网络等，只读，转发 9007）"""
    return await _neuops_forward("ops_entities", "/api/ops/entities", {"type": type})


@app.post("/tools/ops_topology")
@app.get("/tools/ops_topology")
async def ops_topology():
    """获取运维实体拓扑关系（只读，转发 9007）"""
    return await _neuops_forward("ops_topology", "/api/ops/topology")


@app.post("/tools/ops_metrics")
@app.get("/tools/ops_metrics")
async def ops_metrics(
    entity_type: str = Query(default="", description="实体类型"),
    entity_name: str = Query(default="", description="实体名"),
    metric: str = Query(default="", description="指标名：cpu_usage/mem_usage/disk_usage/load1/tcp_conns等"),
    minutes: int = Query(default=10, ge=1, le=1440, description="时间窗（分钟）"),
):
    """查询运维监控时序指标（真实探针采集，只读，转发 9007）"""
    return await _neuops_forward("ops_metrics", "/api/ops/metrics",
                                 {"entity_type": entity_type, "entity_name": entity_name,
                                  "metric": metric, "minutes": minutes})


@app.post("/tools/ops_settings")
@app.get("/tools/ops_settings")
async def ops_settings():
    """获取监控平台配置项（阈值/探针/自愈开关等，只读，转发 9007）"""
    return await _neuops_forward("ops_settings", "/api/ops/settings")


@app.post("/tools/ops_logs")
@app.get("/tools/ops_logs")
async def ops_logs(
    source: str = Query(default="", description="日志来源"),
    level: str = Query(default="", description="级别：error/warn/info/debug"),
    minutes: int = Query(default=10, ge=1, le=1440, description="时间窗（分钟）"),
    limit: int = Query(default=50, ge=1, le=200, description="条数"),
):
    """检索系统日志（真实日志采集，只读，转发 9007）"""
    return await _neuops_forward("ops_logs", "/api/ops/logs",
                                 {"source": source, "level": level,
                                  "minutes": minutes, "limit": limit})


@app.post("/tools/ops_incidents")
@app.get("/tools/ops_incidents")
async def ops_incidents(state: str = Query(default="", description="按状态过滤：detected/repairing/verifying/recovered/failed/manual")):
    """查询故障事件列表（真实事件，只读，转发 9007）"""
    return await _neuops_forward("ops_incidents", "/api/ops/incidents", {"state": state})


@app.post("/tools/ops_alerts_aggregate")
@app.get("/tools/ops_alerts_aggregate")
async def ops_alerts_aggregate(status: str = Query(default="firing", description="告警状态：firing/resolved/all")):
    """查询告警聚合统计（去重降噪后的告警，只读，转发 9007）"""
    return await _neuops_forward("ops_alerts_aggregate", "/api/ops/alerts/aggregate", {"status": status})


@app.post("/tools/monitor_agents")
@app.get("/tools/monitor_agents")
async def monitor_agents():
    """查询全部数字员工（智能体）运行状态（AI自监控，只读，转发 9007）"""
    return await _neuops_forward("monitor_agents", "/api/monitor/agents")


@app.post("/tools/monitor_alerts")
@app.get("/tools/monitor_alerts")
async def monitor_alerts(status: str = Query(default="firing", description="告警状态：firing/resolved"), limit: int = Query(default=100, ge=1, le=500)):
    """查询 AI 智能体异常告警（AI自监控，只读，转发 9007）"""
    return await _neuops_forward("monitor_alerts", "/api/monitor/alerts", {"status": status, "limit": limit})


@app.post("/tools/monitor_alert_rules")
@app.get("/tools/monitor_alert_rules")
async def monitor_alert_rules():
    """查询 AI 智能体告警规则（AI自监控，只读，转发 9007）"""
    return await _neuops_forward("monitor_alert_rules", "/api/monitor/alert-rules")


@app.post("/tools/monitor_timeseries")
@app.get("/tools/monitor_timeseries")
async def monitor_timeseries(days: int = Query(default=7, ge=1, le=90, description="统计天数")):
    """查询 AI 智能体任务/调用时序统计（AI自监控，只读，转发 9007）"""
    return await _neuops_forward("monitor_timeseries", "/api/monitor/timeseries", {"days": days})


@app.post("/tools/long_tasks")
@app.get("/tools/long_tasks")
async def long_tasks():
    """查询数字员工长任务队列（AI自监控，只读，转发 9007）"""
    return await _neuops_forward("long_tasks", "/api/long-tasks")


# ═══════════════════════════════════════════
# 研发类：9006 代码仓库工具（转发 9006）
# ═══════════════════════════════════════════

@app.post("/tools/list_project_files")
@app.get("/tools/list_project_files")
async def list_project_files():
    """列出 9006 项目代码文件（只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/code/files")
            data = r.json()
    except Exception as e:
        return tool_response("list_project_files", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("list_project_files", True, data, source="9006")


@app.post("/tools/read_code_file")
@app.get("/tools/read_code_file")
async def read_code_file(
    file_path: str = Query(default=""),
):
    """读取 9006 项目文件内容（只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/code/file",
                                 params={"path": file_path})
            data = r.json()
    except Exception as e:
        return tool_response("read_code_file", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("read_code_file", True, data, source="9006", path=file_path)


@app.post("/tools/edit_code_file")
@app.get("/tools/edit_code_file")
async def edit_code_file(
    file_path: str = Query(default=""),
    old_text: str = Query(default=""),
    new_text: str = Query(default=""),
):
    """编辑 9006 项目文件（写入，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{BIZ_9006_BASE}/api/code/edit",
                                  json={"path": file_path, "old_text": old_text, "new_text": new_text})
            data = r.json()
    except Exception as e:
        return tool_response("edit_code_file", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("edit_code_file", True, data, source="9006", path=file_path)


@app.post("/tools/search_code")
@app.get("/tools/search_code")
async def search_code(
    keyword: str = Query(default=""),
):
    """搜索 9006 项目代码（只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/code/search",
                                 params={"keyword": keyword})
            data = r.json()
    except Exception as e:
        return tool_response("search_code", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("search_code", True, data, source="9006", keyword=keyword)


@app.post("/tools/write_new_file")
@app.get("/tools/write_new_file")
async def write_new_file(
    file_path: str = Query(default=""),
    content: str = Query(default=""),
):
    """新建 9006 项目文件（写入，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{BIZ_9006_BASE}/api/code/new",
                                  json={"path": file_path, "content": content})
            data = r.json()
    except Exception as e:
        return tool_response("write_new_file", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("write_new_file", True, data, source="9006", path=file_path)


@app.post("/tools/run_shell")
@app.get("/tools/run_shell")
async def run_shell(
    command: str = Query(default=""),
):
    """执行 9006 白名单只读验证命令（转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/code/run",
                                 params={"command": command})
            data = r.json()
    except Exception as e:
        return tool_response("run_shell", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("run_shell", True, data, source="9006", command=command)


# ═══════════════════════════════════════════
# 辅助端点: 工具发现、健康检查
# ═══════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "data_source": DATA_SOURCE}


@app.get("/tools")
async def list_tools():
    """工具发现端点：供页面 / 数字员工同步可用工具（与 MCP_TOOL_SEED 一致）"""
    from seed_data import MCP_TOOL_SEED
    tools = [
        {
            "name": t["id"], "method": t.get("method", "POST"),
            "desc": t.get("desc", ""),
            "params": [p.get("name") for p in (t.get("params_schema") or [])],
            "path": t.get("path", f"/tools/{t['id']}"),
            "category": t.get("category", ""),
            "danger": t.get("danger", 0),
            "params_schema": t.get("params_schema", []),
        }
        for t in MCP_TOOL_SEED
    ]
    return {"tools": tools, "count": len(tools), "data_source": DATA_SOURCE}


# ═══════════════════════════════════════════
# 真实数据源占位函数 (后续替换)
# ═══════════════════════════════════════════

async def _real_get_business_metric(service: str, metric: str):
    """TODO: 对接 Prometheus / 监控系统 API"""
    return tool_response("get_business_metric", False, {"error": "真实数据源未配置"},
                         hint="请在 .env 中配置 PROMETHEUS_URL 等参数")


async def _real_search_service_log(service: str, level: str, limit: int):
    """TODO: 对接 ELK / Loki / 日志系统 API"""
    return tool_response("search_service_log", False, {"error": "真实数据源未配置"})


async def _real_query_cmdb_topology(app: str):
    """TODO: 对接 CMDB REST API"""
    return tool_response("query_cmdb_topology", False, {"error": "真实数据源未配置"})


async def _real_query_change_record(service: str, hours: int):
    """TODO: 对接 ITSM / 变更管理 API"""
    return tool_response("query_change_record", False, {"error": "真实数据源未配置"})


async def _real_query_alarm_info(service: str):
    """TODO: 对接告警平台 API"""
    return tool_response("query_alarm_info", False, {"error": "真实数据源未配置"})


async def _real_run_auto_job(job_type: str, target: str):
    """TODO: 对接自动化作业平台 API"""
    return tool_response("run_auto_job", False, {"error": "真实数据源未配置"})


# ═══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9010)
