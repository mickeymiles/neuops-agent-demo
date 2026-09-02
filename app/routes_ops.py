# -*- coding: utf-8 -*-
"""运维监控 API：/api/ops/*（一体化运维监控平台后端）

覆盖：总览 / 六类实体 / 本体拓扑 / 时序查询 / 告警规则 / 配置中心 /
探针控制（手动采集、远程探针上报）
"""
import socket
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from . import db, ops_ontology
from .probe import ProbeManager

router = APIRouter(prefix="/api/ops", tags=["ops"])

# 部署指纹：每次上线部署时手工 +1，用于线上核对「当前进程跑的是不是最新代码」。
# 背景：曾出现 CI 全绿、健康检查通过，但 9007 端口被旧孤儿进程霸占，线上仍是旧逻辑。
# 本接口让一次 curl 就能判定线上到底加载了哪份代码。
DEPLOY_BUILD = "2026-09-03.2-tz-fix-orphan-kill"


@router.get("/deploy-info")
def deploy_info():
    """返回当前进程加载的代码部署指纹，便于核对线上是否真的换成了新代码。"""
    return {
        "ok": True,
        "build": DEPLOY_BUILD,
        "deploy_path": str(Path(__file__).resolve().parent.parent),
    }

# /ops 一体化运维监控平台页面路由（无 /api 前缀，供浏览器直接访问）
page_router = APIRouter(tags=["ops-page"])

OPS_HTML = Path(__file__).resolve().parent.parent / "static" / "ops.html"

# 全局探针实例（由 main.py 启动；此处负责手动采集等）
_probe = None  # type: Optional[ProbeManager]


def set_probe(pm):
    global _probe
    _probe = pm


def get_probe():
    return _probe


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@router.get("/page")
def ops_page():
    """/ops 页面（独立一体化运维监控平台）"""
    if not OPS_HTML.exists():
        raise HTTPException(404, "ops.html not found")
    return FileResponse(str(OPS_HTML))


@page_router.get("/ops")
def ops_page_root():
    """/ops 一体化运维监控平台页面（浏览器直接访问入口）"""
    if not OPS_HTML.exists():
        raise HTTPException(404, "ops.html not found")
    return FileResponse(str(OPS_HTML))


# ---------------- 总览 ----------------

@router.get("/overview")
def ops_overview():
    entities = db.ops_get_entities()
    by_type = {}
    by_status = {}
    for e in entities:
        by_type.setdefault(e["type"], []).append(e)
        by_status.setdefault(e["status"], []).append(e)
    # 告警统计
    alerts = db._query_rows(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN status='firing' THEN 1 ELSE 0 END) AS firing "
        "FROM alerts")
    a = alerts[0] if alerts else {"n": 0, "firing": 0}
    # 最近指标快照
    snapshot = db.ops_get_latest_snapshot()
    server_snapshot = {}
    for (et, en), m in snapshot.items():
        if et == "server":
            server_snapshot[en] = m
    return {
        "ok": True,
        "updatedAt": _now(),
        "probe": {
            "running": bool(_probe and _probe._thread and _probe._thread.is_alive()),
            "lastRunAt": _probe.last_run_at if _probe else "",
            "interval": _probe.interval if _probe else 30,
            "collectors": _probe.collector_names() if _probe else [],
            "lastError": _probe.last_error if _probe else "",
        },
        "entities": {
            "total": len(entities),
            "byType": {t: len(by_type.get(t, [])) for t in ops_ontology.ENTITY_TYPES},
            "byStatus": {s: len(by_status.get(s, [])) for s in ops_ontology.STATUS_META},
            "types": ops_ontology.ENTITY_META,
        },
        "alerts": {"total": a["n"] or 0, "firing": a["firing"] or 0},
        "serverSnapshot": server_snapshot,
    }


# ---------------- 本体实体 ----------------

@router.get("/entities")
def ops_entities(type: str = Query("", description="实体类型：server/database/network/container/middleware/application")):
    return {"ok": True, "entities": db.ops_get_entities(type), "types": ops_ontology.ENTITY_META}


@router.get("/entities/{entity_id}")
def ops_entity_detail(entity_id: str):
    e = db.ops_get_entity(entity_id)
    if not e:
        raise HTTPException(404, f"entity {entity_id} not found")
    graph = ops_ontology.build_entity_graph(entity_id)
    # 该实体最近 1 小时时序
    metrics = db.ops_get_metrics(
        entity_type=e["type"], entity_name=e["name"], minutes=60)
    return {"ok": True, "entity": e, "graph": graph, "metrics": metrics}


# ---------------- 本体拓扑 ----------------

@router.get("/topology")
def ops_topology():
    return {"ok": True, "topology": ops_ontology.build_topology()}


# ---------------- 时序查询 ----------------

@router.get("/metrics")
def ops_metrics(
    entity_type: str = Query("", description="实体类型"),
    entity_name: str = Query("", description="实体名"),
    metric: str = Query("", description="指标名"),
    minutes: int = Query(10, ge=1, le=1440, description="时间窗（分钟）"),
):
    rows = db.ops_get_metrics(entity_type=entity_type, entity_name=entity_name,
                              metric=metric, minutes=minutes)
    return {"ok": True, "metrics": rows, "count": len(rows)}


# ---------------- 配置中心（settings） ----------------

# 页面可配置项定义：key -> {label, type, default, desc, group}
SETTINGS_DEF = {
    "feishu_webhook": {"label": "飞书机器人 Webhook", "type": "text", "default": "",
                       "desc": "飞书群机器人 webhook 地址，留空则告警仅入库不推送", "group": "飞书告警"},
    "feishu_secret": {"label": "飞书签名密钥", "type": "text", "default": "",
                      "desc": "飞书自定义机器人加签 secret（可选）", "group": "飞书告警"},
    "probe_interval": {"label": "探针采集周期（秒）", "type": "number", "default": "30",
                       "desc": "统一探针采集间隔，默认 30 秒", "group": "探针"},
    "retention_days": {"label": "时序数据保留（天）", "type": "number", "default": "1",
                       "desc": "ops_metrics 保留天数，超期自动清理", "group": "探针"},
    "cpu_threshold": {"label": "CPU 使用率告警阈值（%）", "type": "number", "default": "90", "group": "告警阈值"},
    "mem_threshold": {"label": "内存使用率告警阈值（%）", "type": "number", "default": "90", "group": "告警阈值"},
    "disk_threshold": {"label": "磁盘使用率告警阈值（%）", "type": "number", "default": "90", "group": "告警阈值"},
    "probe_apps": {"label": "自定义监控应用", "type": "textarea", "default": "",
                   "desc": "格式：名称|http://地址|端口|进程关键词，每行一个，用 | 分隔", "group": "应用采集"},
    "app_9006_log": {"label": "9006 应用日志路径", "type": "text", "default": "",
                     "desc": "9006 contract-compare 日志文件路径（统一探针增量采集）", "group": "日志采集"},
    "app_9007_log": {"label": "9007 应用日志路径", "type": "text", "default": "",
                     "desc": "9007 neuops 自身日志文件路径（统一探针增量采集）", "group": "日志采集"},
}


@router.get("/settings")
def ops_get_settings():
    stored = db.db_get_settings_all()
    out = {}
    for key, meta in SETTINGS_DEF.items():
        out[key] = {"key": key, **meta, "value": stored.get(key, meta["default"])}
    return {"ok": True, "settings": out, "defs": SETTINGS_DEF}


@router.put("/settings")
def ops_update_settings(payload: dict = Body(...)):
    updated = []
    for key, value in payload.items():
        if key not in SETTINGS_DEF:
            continue
        db.db_set_setting(key, str(value))
        updated.append(key)
    # 动态应用探针周期
    pm = get_probe()
    if pm and "probe_interval" in updated:
        try:
            pm.interval = int(db.db_get_setting("probe_interval", "30"))
        except ValueError:
            pass
    return {"ok": True, "updated": updated}


# ---------------- 告警规则（复用 alert_rules 表） ----------------

@router.get("/alert-rules")
def ops_alert_rules():
    rows = db._query_rows("SELECT * FROM alert_rules ORDER BY severity DESC, id")
    return {"ok": True, "rules": [dict(r) for r in rows]}


@router.post("/alert-rules")
def ops_create_alert_rule(payload: dict = Body(...)):
    rid = payload.get("id") or "rule-" + uuid.uuid4().hex[:8]
    with db._db_lock:
        conn = db._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO alert_rules (id, name, metric, target, threshold, window_min, severity, enabled, desc) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, payload.get("name", ""), payload.get("metric", ""),
                 payload.get("target", ""), float(payload.get("threshold", 0)),
                 int(payload.get("window_min", 10)), payload.get("severity", "warning"),
                 1 if payload.get("enabled", True) else 0,
                 payload.get("desc", "")))
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "id": rid}


@router.put("/alert-rules/{rule_id}")
def ops_update_alert_rule(rule_id: str, payload: dict = Body(...)):
    with db._db_lock:
        conn = db._get_conn()
        try:
            conn.execute(
                "UPDATE alert_rules SET name=?, metric=?, target=?, threshold=?, window_min=?, severity=?, enabled=?, desc=? WHERE id=?",
                (payload.get("name", ""), payload.get("metric", ""), payload.get("target", ""),
                 float(payload.get("threshold", 0)), int(payload.get("window_min", 10)),
                 payload.get("severity", "warning"), 1 if payload.get("enabled", True) else 0,
                 payload.get("desc", ""), rule_id))
            conn.commit()
        finally:
            conn.close()
    return {"ok": True}


@router.delete("/alert-rules/{rule_id}")
def ops_delete_alert_rule(rule_id: str):
    with db._db_lock:
        conn = db._get_conn()
        try:
            conn.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
            conn.commit()
        finally:
            conn.close()
    return {"ok": True}


# ---------------- 统一日志（ops_logs） ----------------

@router.get("/logs")
def ops_logs(
    source: str = Query("", description="来源过滤，如 app:neuops / system:syslog"),
    level: str = Query("", description="级别过滤：error/warn/info/debug"),
    minutes: int = Query(30, ge=1, le=1440, description="时间窗（分钟）"),
    limit: int = Query(200, ge=1, le=2000),
):
    rows = db.ops_get_logs(source=source, level=level, minutes=minutes, limit=limit)
    # 同时返回各级别计数（用于告警/图表）
    stats = {
        "error": db.ops_count_logs(minutes=minutes, level="error"),
        "warn": db.ops_count_logs(minutes=minutes, level="warn"),
        "info": db.ops_count_logs(minutes=minutes, level="info"),
        "debug": db.ops_count_logs(minutes=minutes, level="debug"),
        "total": db.ops_count_logs(minutes=minutes),
    }
    return {"ok": True, "logs": rows, "stats": stats, "count": len(rows)}


@router.get("/alerts/aggregate")
def ops_alerts_aggregate(status: str = Query("firing", description="告警状态筛选：firing/resolved/all")):
    """告警中心聚合：返回告警(alerts)统一列表。"""
    if status not in ("firing", "resolved", "all"):
        status = "firing"
    if status == "all":
        alerts = db._query_rows("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (100,))
    else:
        alerts = db._query_rows("SELECT * FROM alerts WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, 100))
    return {
        "ok": True,
        "alerts": alerts,
    }


# ---------------- 探针控制 ----------------

@router.get("/probe/status")
def ops_probe_status():
    pm = get_probe()
    return {
        "ok": True,
        "running": bool(pm and pm._thread and pm._thread.is_alive()),
        "interval": pm.interval if pm else 30,
        "lastRunAt": pm.last_run_at if pm else "",
        "collectors": pm.collector_names() if pm else [],
        "lastError": pm.last_error if pm else "",
        "lastReports": {k: {"ok": v.ok, "error": v.error,
                            "metrics": len(v.metrics), "entities": len(v.entities),
                            "relations": len(v.relations), "logs": len(v.logs)}
                        for k, v in (pm.last_reports.items() if pm else {})},
    }


@router.post("/probe/run-now")
def ops_probe_run_now():
    pm = get_probe()
    if not pm:
        pm = ProbeManager()
        set_probe(pm)
    summary = pm.run_once()
    return {"ok": True, "summary": summary, "collectedAt": pm.last_run_at}


@router.post("/probe/ingest")
async def ops_probe_ingest(request: Request, payload: dict = Body(...)):
    """远程探针上报入口：独立探针进程通过 HTTP 上报采集结果（按主机名隔离，多探针共存）"""
    try:
        ts = payload.get("collected_at") or _now()
        hostname = (payload.get("hostname") or "").strip() or "remote"
        scope = hostname
        remote_ip = ""
        try:
            remote_ip = request.client.host if request.client else ""
        except Exception:  # noqa: BLE001
            pass
        collectors = payload.get("collectors", {})
        metrics, entities, relations, logs = [], [], [], []
        for _, cdata in collectors.items():
            if not cdata.get("ok"):
                continue
            # metric 归一化：兼容 (etype, ename, metric, value) 与 (..., unit) 两种上报格式
            for m in cdata.get("metrics", []):
                m = tuple(m) if isinstance(m, list) else m
                if len(m) == 4:
                    m = (*m, "")
                metrics.append(m)
            entities.extend(cdata.get("entities", []))
            relations.extend(tuple(r) if isinstance(r, list) else r for r in cdata.get("relations", []))
            logs.extend(tuple(l) if isinstance(l, list) else l for l in cdata.get("logs", []))
        # 与监控中心主机名冲突防御（罕见）：远程指标/实体加 @remote 后缀避免覆盖本机数据
        if hostname and hostname == socket.gethostname():
            metrics = [tuple((m[0], f"{m[1]}@remote", *m[2:])) for m in metrics]
            for e in entities:
                e["name"] = e["name"] + "@remote"
        # 实体/关系 id 加来源主机前缀，保证多探针实体共存且互不覆盖
        prefix = f"{scope}:"
        entities = [{**e, "id": prefix + e["id"],
                     "attrs": {**(e.get("attrs") or {}), "remote_host": hostname,
                               **({"remote_ip": remote_ip} if remote_ip else {})}}
                    for e in entities]
        relations = [(prefix + r[0], prefix + r[1], *r[2:]) for r in relations]
        if metrics:
            db.ops_save_metrics(ts, metrics)
        if entities:
            db.ops_save_entities(ts, entities, scope=scope)
        if relations:
            db.ops_save_relations(ts, relations, scope=scope)
        if logs:
            # 远程日志 source 加主机前缀，避免与本机日志告警规则混用
            db.ops_save_logs([(ts, f"{scope}:{s}", lv, msg) for s, lv, msg in logs])
        return {"ok": True, "entityCount": len(entities), "metricCount": len(metrics),
                "logCount": len(logs), "probe": payload.get("probe", ""),
                "hostname": hostname, "scope": scope}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"ingest error: {e}")
