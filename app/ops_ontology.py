# -*- coding: utf-8 -*-
"""运维本体：六类实体 + 三类关系，从探针采集的真实数据构建本体拓扑

实体类型（ENTITY_TYPES）：
    server      服务器（CPU/内存/磁盘/负载/进程/网络IO）
    database    数据库（SQLite/MySQL/PostgreSQL 真实检测）
    network     网络（网卡/连接/端口监听）
    container   容器（docker 真实命令）
    middleware  中间件（Redis/MySQL/Nginx 等端口+进程探测）
    application 应用（9006/9007 HTTP 健康 + 进程）

关系类型（RELATION_TYPES）：
    runs_on     运行于（容器/中间件/应用 -> 服务器）
    hosted_on   承载于（数据库/网络 -> 服务器）
    connects_to 连接至（应用 -> 数据库/中间件）
"""
from . import db

ENTITY_TYPES = ("server", "database", "network", "container", "middleware", "application")
RELATION_TYPES = ("runs_on", "hosted_on", "connects_to")

# 本体类型元数据：配色 / 图标 / 展示名（前端拓扑渲染使用）
ENTITY_META = {
    "server":       {"label": "服务器",     "color": "#4f8cff", "icon": "server"},
    "database":     {"label": "数据库",     "color": "#34d399", "icon": "database"},
    "network":      {"label": "网络",       "color": "#22d3ee", "icon": "network"},
    "container":    {"label": "容器",       "color": "#a78bfa", "icon": "container"},
    "middleware":   {"label": "中间件",     "color": "#fb923c", "icon": "middleware"},
    "application":  {"label": "应用",       "color": "#fbbf24", "icon": "application"},
}
RELATION_META = {
    "runs_on":    {"label": "运行于", "color": "#22d3ee"},
    "hosted_on":  {"label": "承载于", "color": "#34d399"},
    "connects_to": {"label": "连接至", "color": "#fbbf24"},
}

# 状态元数据：色值（前端状态灯）
STATUS_META = {
    "running":  {"label": "运行中", "color": "#34d399"},
    "degraded": {"label": "异常",   "color": "#fbbf24"},
    "down":     {"label": "宕机",   "color": "#f87171"},
    "unknown":  {"label": "未知",   "color": "#7d8db0"},
}


def entity_type_label(etype: str) -> str:
    return ENTITY_META.get(etype, {}).get("label", etype)


def build_topology() -> dict:
    """从真实采集数据构建本体拓扑（ECharts graph 格式）"""
    entities = db.ops_get_entities()
    relations = db.ops_get_relations()

    nodes = []
    for e in entities:
        meta = ENTITY_META.get(e["type"], {})
        nodes.append({
            "id": e["id"],
            "name": e["name"],
            "type": e["type"],
            "typeLabel": meta.get("label", e["type"]),
            "status": e["status"],
            "statusLabel": STATUS_META.get(e["status"], {}).get("label", e["status"]),
            "color": meta.get("color", "#7d8db0"),
            "statusColor": STATUS_META.get(e["status"], {}).get("color", "#7d8db0"),
            "metrics": e.get("metrics", {}),
            "attrs": e.get("attrs", {}),
            "updatedAt": e.get("updated_at", ""),
        })

    edges = []
    for r in relations:
        meta = RELATION_META.get(r["type"], {})
        edges.append({
            "source": r["source"],
            "target": r["target"],
            "type": r["type"],
            "typeLabel": meta.get("label", r["type"]),
            "color": meta.get("color", "#7d8db0"),
        })

    # 统计
    summary = {"total": len(nodes), "byType": {}, "byStatus": {}}
    for n in nodes:
        summary["byType"][n["type"]] = summary["byType"].get(n["type"], 0) + 1
        summary["byStatus"][n["status"]] = summary["byStatus"].get(n["status"], 0) + 1

    return {"nodes": nodes, "edges": edges, "summary": summary,
            "entityMeta": ENTITY_META, "relationMeta": RELATION_META,
            "statusMeta": STATUS_META}


def build_entity_graph(entity_id: str) -> dict:
    """单个实体 + 其直接关系的一跳子图"""
    all_topo = build_topology()
    entity = next((n for n in all_topo["nodes"] if n["id"] == entity_id), None)
    if not entity:
        return {"nodes": [], "edges": [], "summary": {}, "entityMeta": ENTITY_META,
                "relationMeta": RELATION_META, "statusMeta": STATUS_META}
    related_ids = {entity_id}
    edges = []
    for e in all_topo["edges"]:
        if e["source"] == entity_id or e["target"] == entity_id:
            related_ids.add(e["source"])
            related_ids.add(e["target"])
            edges.append(e)
    nodes = [n for n in all_topo["nodes"] if n["id"] in related_ids]
    return {"nodes": nodes, "edges": edges,
            "summary": {"total": len(nodes)}, "entityMeta": ENTITY_META,
            "relationMeta": RELATION_META, "statusMeta": STATUS_META}
