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
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from mock_data import (
    MOCK_METRICS, MOCK_LOGS, MOCK_CMDB,
    MOCK_CHANGES, MOCK_ALARMS,
    MOCK_BIZ_METRICS, MOCK_BID_KB, MOCK_BID_TEMPLATES,
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

async def merge_params(request, **query):
    """合并入参：POST/PUT body 优先，query 兜底（★防「body 参数被静默丢弃」）。

    历史缺陷（ontology_compute 曾中招，PM 域工具同样存在）：工具只声明 Query(...) 参数，
    而智能体多以 JSON body 传参 → 参数静默丢失，工具用默认值算出结果且 success 仍为 true，
    比显式报错危险得多。故所有接受入参的工具统一走本函数。
    """
    body = {}
    if request is not None and request.method in ("POST", "PUT", "PATCH"):
        try:
            raw = await request.body()
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    body = parsed
        except Exception:
            body = {}
    out = dict(query)
    for k, v in body.items():
        # 仅当 body 值非空时才覆盖（避免空值把 query 的有效值冲掉）
        if v not in (None, ""):
            out[k] = v
    return out


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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/mcp/ontology/schema",
                                 params={"table_name": table_name})
            data = r.json()
    except Exception as e:
        return tool_response("get_table_schema", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("get_table_schema", True, data,
                         source="9006", table_name=table_name)


# ═══════════════════════════════════════════
# 经营业务：本体计算（★直调共享 ontos 子模块，不经 9006 HTTP API）
# ═══════════════════════════════════════════

@app.post("/tools/ontology_compute")
@app.get("/tools/ontology_compute")
async def ontology_compute(
    request: Request,
    function: str = Query(default=""),
    params: str = Query(default="{}"),
):
    """本体计算（经营语义计算，★直调共享 ontos，与 9006 固化显示同一份代码）。

    2026-09-05 用户拍板（同源）：本体的计算供 9006 与 9007 共用，9007 不得经 9006 的
    函数 API 取数——原「转发 9006 /api/ontos/compute」已废弃，改为本地 import 共享
    ontos 子模块。ABox 场景函数（如 cost_warning_portfolio）由 ontos.abox_cost 直读
    业务库 SQLite（环境变量 ONTOS_DB_PATH，默认同机 ../contract-compare/contract_compare.db），
    与 9006 成本预警页面同源。
    参数：function=函数名(或 F-xxx)；params=JSON 字符串（GET query）或 JSON body（POST）。

    入参优先级：POST body > query string。
    params 可接受 dict（body）或 JSON 字符串（body/query 皆可）。
    """
    import json as _json

    # ---- 读取 POST body（若为 GET 或空 body 则忽略）----
    body = {}
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            raw = await request.body()
            if raw:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    body = parsed
        except Exception:
            body = {}

    # function：body 优先，query 兜底
    function = body.get("function") or function

    # params：body 优先，query 兜底；支持 dict 或 JSON 字符串
    raw_params = body.get("params", None)
    if raw_params is None:
        raw_params = params if params else "{}"
    if isinstance(raw_params, dict):
        p = raw_params
    else:
        try:
            p = _json.loads(raw_params) if raw_params else {}
        except Exception:
            p = {}
    if not isinstance(p, dict):
        p = {}
    try:
        from app import ontos_compute as _oc
        data = _oc.compute(function, p)
    except Exception as e:
        return tool_response("ontology_compute", False,
                             {"error": f"本体计算失败: {e}"}, function=function)
    return tool_response("ontology_compute", data.get("success", False), data,
                         source="ontos", function=function)


# ═══════════════════════════════════════════
# 经营业务：合同比对引擎（转发 9006）
# ═══════════════════════════════════════════

@app.post("/tools/query_contracts")
@app.get("/tools/query_contracts")
async def query_contracts():
    """获取全部合同及比对进度概览（合同比对引擎，只读，转发 9006）"""
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
    """获取监控平台配置项（阈值/探针等，只读，转发 9007）"""
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            r = await client.get(f"{BIZ_9006_BASE}/api/code/run",
                                 params={"command": command})
            data = r.json()
    except Exception as e:
        return tool_response("run_shell", False,
                             {"error": f"无法连接9006经营分析系统: {e}"})
    return tool_response("run_shell", True, data, source="9006", command=command)


# ═══════════════════════════════════════════
# 项目管理域工具（两单一物/四算/工时/成本，全部只读研判）
# ═══════════════════════════════════════════

@app.post("/tools/pm_project_read")
@app.get("/tools/pm_project_read")
async def pm_project_read(
    request: Request,
    project_id: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
):
    """查询项目档案与成本执行（★读共享本体 ontos，真实业务数据）。

    数据源：项目主数据 md_contract（合同:项目=1:1，project_id 即合同编号）。
    含：部门/责任人/区域/合同状态/签约额 + 预算/当前成本 + 本体 F-project-cost-warning 判定。
    ⌛四算（概算/预算/核算/决算）未接入 —— 返回 not_available，**不再返回演示数据**。

    ★分页语义（务必遵守）：不传 project_id 时只返回前 limit 条（默认 20），
    响应中 total / total_all / status_count 是**全量统计**，truncated=True 表示被截断。
    **不得把本页条目当作全集**回答「共有 X 个项目」——要总数看 total_all，
    要某类项目用 status=超支/预警/正常 筛选后按 offset 翻页遍历。
    """
    p = await merge_params(request, project_id=project_id, limit=limit, status=status,
                           offset=offset)
    project_id = str(p.get("project_id") or "")
    status = str(p.get("status") or "")
    limit = int(p.get("limit") or 20)
    offset = int(p.get("offset") or 0)
    try:
        from app import ontos_compute as _oc
        res = _oc.project_portfolio(project_id or None, status or None, limit, offset)
        rows = res["items"]
        if project_id and not rows:
            return tool_response("pm_project_read", False,
                                 {"error": f"未在项目主数据中找到项目 {project_id}"
                                           f"（project_id = 合同编号，如 DFSY1410017C）"})
        # ★防「把样本当全集」：明确告知总数、是否截断、如何翻页
        hint = None
        if res["truncated"]:
            hint = (f"⚠ 本次仅返回第 {res['offset'] + 1}-{res['offset'] + res['returned']} 条，"
                    f"符合条件共 {res['total']} 个（全库 {res['total_all']} 个）——"
                    f"**这不是全集**，不得据此回答「共有 X 个项目」；"
                    f"继续取下一页请带 offset={res['next_offset']}，"
                    f"或按 status=超支/预警/正常 筛选后分页遍历。")
        return tool_response("pm_project_read", True, {
            "projects": rows,
            "count": res["returned"],          # 本页条数
            "total": res["total"],             # 筛选后全量
            "total_all": res["total_all"],     # 全库
            "truncated": res["truncated"],
            "next_offset": res["next_offset"],
            "status_count": res["status_count"],   # ★全库分布，不是本页分布
            "hint": hint,                          # 截断时的翻页/口径提示
            # ⌛未接入：四算与里程碑如实标注，杜绝智能体拿假数据作答
            "four_calc": _oc.not_available("four_calc"),
            "note": "数据源=共享本体 ontos（md_contract 项目主数据），与 9006 成本预警同源；"
                    "project_id 即合同编号；预算=累计实施成本预估、成本=累计实施成本实际。",
        }, source="ontos")
    except Exception as e:
        return tool_response("pm_project_read", False,
                             {"error": f"本体读取失败: {type(e).__name__}: {e}"})


@app.post("/tools/pm_task_read")
@app.get("/tools/pm_task_read")
async def pm_task_read(
    request: Request,
    project_id: str = Query(default=""),
    status: str = Query(default=""),
):
    """查询两单一物工单、任务明细与状态。

    ⌛**数据源未接入**（plm_task / plm_assignment 均为空表）。★红线：此处曾返回
    MOCK_PM_TASKS 演示数据，导致智能体拿假工单作答；现改为显式返回 not_available，
    不做估算、不返回演示数据。
    """
    from app import ontos_compute as _oc
    return tool_response("pm_task_read", False, {
        "tasks": [],
        **_oc.not_available("task"),
    }, source="ontos", project_id=project_id)


@app.post("/tools/pm_workhour_read")
@app.get("/tools/pm_workhour_read")
async def pm_workhour_read(
    request: Request,
    project_id: str = Query(default=""),
    date: str = Query(default=""),
):
    """查询日报、工时明细与人员填报数据。

    ⌛**数据源未接入**（md_contract 205 列无工时列，plm_timesheet 等表为空，PMO 域未建设）。
    ★红线：此处曾返回 MOCK_PM_WORKHOURS 演示数据（含假合规率），现改为显式 not_available。
    """
    from app import ontos_compute as _oc
    return tool_response("pm_workhour_read", False, {
        "records": [],
        "compliance_rate": None,
        "abnormal_records": [],
        **_oc.not_available("workhour"),
    }, source="ontos")


@app.post("/tools/pm_cost_calc")
@app.get("/tools/pm_cost_calc")
async def pm_cost_calc(
    request: Request,
    project_id: str = Query(default=""),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
):
    """项目成本明细（★读共享本体 ontos.abox_cost，真实业务数据）。

    返回预算三分量（硬件集成费/服务预估成本/软件预估实施费）与成本六分量
    （硬件集成费实际/软件实际实施费/往年·当年实际服务直接·间接）+ 本体预警判定。
    口径与 9006 成本预警页同源。

    ★分页语义：不传 project_id 时只返回前 limit 条，total 为全量条数，
    truncated=True 时须带 offset=next_offset 继续翻页，不得把本页当全集。
    """
    p = await merge_params(request, project_id=project_id, limit=limit, offset=offset)
    project_id = str(p.get("project_id") or "")
    limit = int(p.get("limit") or 20)
    offset = int(p.get("offset") or 0)
    try:
        from app import ontos_compute as _oc
        res = _oc.cost_detail_page(project_id or None, limit, offset)
        costs = res["items"]
        if project_id and not costs:
            return tool_response("pm_cost_calc", False,
                                 {"error": f"未找到项目 {project_id} 的成本数据"})
        return tool_response("pm_cost_calc", True, {
            "costs": costs,
            "count": res["returned"],
            "total": res["total"],
            "truncated": res["truncated"],
            "next_offset": res["next_offset"],
            "hint": (f"⚠ 本页 {res['returned']} 条 / 共 {res['total']} 条，非全集；"
                     f"翻页带 offset={res['next_offset']}") if res["truncated"] else None,
            "note": "数据源=共享本体 ontos（md_contract），预算/成本分量列名取 "
                    "COST_FORMULA_POLICY，与 9006 成本预警同源；"
                    "人力成本折算依赖工时数据，当前 ⌛未接入。",
        }, source="ontos")
    except Exception as e:
        return tool_response("pm_cost_calc", False,
                             {"error": f"本体读取失败: {type(e).__name__}: {e}"})


@app.post("/tools/biz_metric_read")
@app.get("/tools/biz_metric_read")
async def biz_metric_read(
    metric_name: str = Query(default=""),
    period: str = Query(default=""),
):
    """读取预计算经营&项目集团指标（人均效/元效/双按完成率/四算偏差）。

    ⚠ **本工具仍为演示数据（MOCK_BIZ_METRICS），非本体真实数据**：集团预计算指标
    尚未接入本体。响应体带 data_status.available=False 与 demo=True 标记，
    智能体须如实说明「该指标为演示数据」，不得当作真实经营指标引用。
    """
    demo_warn = {
        "available": False,
        "demo": True,
        "blocked_by": "集团预计算指标（人均效/元效/双按完成率/四算偏差）尚未接入本体",
        "message": "以下为演示数据（MOCK_BIZ_METRICS），不是本体真实数据；"
                   "回答时须明确标注为演示口径。",
    }
    if metric_name and metric_name in MOCK_BIZ_METRICS:
        metric = dict(MOCK_BIZ_METRICS[metric_name])
        if period and metric.get("period") != period:
            metric["note"] = metric.get("note", "") + f"（当前库内仅有 {metric.get('period')} 周期数据）"
        return tool_response("biz_metric_read", True,
                             {"metric": metric, "data_status": demo_warn}, source="mock")
    if not metric_name:
        return tool_response("biz_metric_read", True,
                             {"metrics": MOCK_BIZ_METRICS, "data_status": demo_warn},
                             source="mock")
    return tool_response("biz_metric_read", False,
                         {"error": f"未找到指标 {metric_name}，可选：{list(MOCK_BIZ_METRICS.keys())}",
                          "data_status": demo_warn}, source="mock")


# ═══════════════════════════════════════════
# 售前投标域工具（知识库/模板/导出，只生成不执行）
# ═══════════════════════════════════════════

@app.post("/tools/kb_knowledge_read")
@app.get("/tools/kb_knowledge_read")
async def kb_knowledge_read(
    keyword: str = Query(default=""),
    limit: int = Query(default=5),
):
    """检索内部知识库、历史方案、中标库"""
    if not keyword:
        return tool_response("kb_knowledge_read", False,
                             {"error": "请提供 keyword 检索关键词"})
    kw = keyword.lower()
    hits = []
    for doc in MOCK_BID_KB:
        text = " ".join([doc["industry"], doc["scenario"], doc["title"], doc["summary"],
                         " ".join(doc["keywords"]), doc["content"]])
        if kw in text.lower():
            hits.append(doc)
    hits = hits[:limit]
    return tool_response("kb_knowledge_read", True,
                         {"keyword": keyword, "hits": hits, "hit_count": len(hits)},
                         source="mock")


@app.post("/tools/bid_template_read")
@app.get("/tools/bid_template_read")
async def bid_template_read(
    template_type: str = Query(default=""),
):
    """读取投标标准模板库与技术规范模板"""
    if template_type:
        if template_type not in MOCK_BID_TEMPLATES:
            return tool_response("bid_template_read", False,
                                 {"error": f"未找到模板 {template_type}，可选：{list(MOCK_BID_TEMPLATES.keys())}"})
        return tool_response("bid_template_read", True,
                             {"template": MOCK_BID_TEMPLATES[template_type]}, source="mock")
    return tool_response("bid_template_read", True, {"templates": MOCK_BID_TEMPLATES}, source="mock")


@app.post("/tools/doc_export")
@app.get("/tools/doc_export")
async def doc_export(
    doc_type: str = Query(default=""),
    title: str = Query(default=""),
):
    """生成结构化投标文档（Word/PPT大纲），供人工下载"""
    if not doc_type or doc_type not in MOCK_BID_TEMPLATES:
        return tool_response("doc_export", False,
                             {"error": f"doc_type 必填且需为 {list(MOCK_BID_TEMPLATES.keys())} 之一"})
    tpl = MOCK_BID_TEMPLATES[doc_type]
    doc_title = title or f"{tpl['name']}-{datetime.now().strftime('%Y%m%d')}"
    sections = tpl["sections"]
    return tool_response("doc_export", True, {
        "doc_title": doc_title,
        "doc_type": doc_type,
        "format": "markdown_structure",
        "template_version": tpl["version"],
        "sections": sections,
        "estimated_pages": max(6, len(sections) * 2),
        "note": "已生成结构化文档大纲，供人工下载后编辑完善；本工具不做任何系统写入",
    }, source="mock")


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
