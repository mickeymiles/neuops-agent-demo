"""AI 智能体监控后台 API 路由（monitor.html 独立页面配套）"""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, RedirectResponse

from .db import (
    _COST_INPUT_PER_M,
    _COST_OUTPUT_PER_M,
    _agent_name_map,
    _db_lock,
    _est_tokens,
    _get_conn,
    _parse_route,
    _query_rows,
    _text_summary,
    db_get_employee,
    db_set_employee_enabled,
)
from .knowledge import EMBED_MODEL

router = APIRouter()


@router.get("/api/monitor/overview")
async def monitor_overview():
    """监控总览：智能体数 / 会话数 / 消息数 / LLM 调用数 / Token / 成本 / 错误率 / 活跃告警 / 今日趋势"""
    agents = _query_rows("SELECT id, name FROM employees ORDER BY id")
    convs = _query_rows("SELECT id, created_at, updated_at FROM conversations")
    msgs = _query_rows("SELECT conversation_id, role, content, created_at FROM messages")
    calls = _query_rows("SELECT total_tokens, prompt_tokens, completion_tokens, latency_ms, error, created_at FROM llm_calls")

    est_tokens = sum(_est_tokens(m["content"]) for m in msgs)
    real_tokens = sum(c["total_tokens"] or 0 for c in calls)
    prompt_tk = sum(c["prompt_tokens"] or 0 for c in calls)
    complet_tk = sum(c["completion_tokens"] or 0 for c in calls)
    cost = prompt_tk / 1e6 * _COST_INPUT_PER_M + complet_tk / 1e6 * _COST_OUTPUT_PER_M

    error_calls = sum(1 for c in calls if c.get("error"))
    ok_lat = [c["latency_ms"] for c in calls if (c["latency_ms"] or 0) > 0]
    avg_latency = round(sum(ok_lat) / len(ok_lat), 1) if ok_lat else 0
    active_alerts = len(_query_rows("SELECT id FROM alerts WHERE status='firing'"))

    today = datetime.now().strftime("%Y-%m-%d")
    today_calls = [c for c in calls if (c["created_at"] or "").startswith(today)]
    today_msgs = [m for m in msgs if (m["created_at"] or "").startswith(today)]
    active_today = set(m["conversation_id"] for m in today_msgs)

    return JSONResponse({"ok": True, "data": {
        "agent_count": len(agents),
        "conversation_count": len(convs),
        "message_count": len(msgs),
        "llm_call_count": len(calls),
        "total_tokens": real_tokens,
        "prompt_tokens": prompt_tk,
        "completion_tokens": complet_tk,
        "est_tokens": est_tokens,
        "est_cost": round(cost, 4),
        "error_calls": error_calls,
        "error_rate": round(error_calls / len(calls) * 100, 2) if calls else 0,
        "avg_latency_ms": avg_latency,
        "active_alerts": active_alerts,
        "today": {
            "llm_call_count": len(today_calls),
            "total_tokens": sum(c["total_tokens"] or 0 for c in today_calls),
            "message_count": len(today_msgs),
            "active_sessions": len(active_today),
        },
    }})


@router.get("/api/monitor/agents")
async def monitor_agents():
    """每个智能体的监控：开关状态 / 基本信息 / 能力配置 / 会话数 / 消息数 / Token / 耗时 / 活跃告警"""
    agents = _query_rows("SELECT * FROM employees ORDER BY id")
    calls = _query_rows("SELECT * FROM llm_calls")
    msgs = _query_rows("SELECT conversation_id, route, content, role, created_at FROM messages")

    # 技能与 MCP 工具映射（整体加载一次，避免 N+1 查询）
    skill_map = {s["id"]: s for s in _query_rows("SELECT id, name, category FROM skills")}
    tool_map = {t["id"]: t for t in _query_rows("SELECT id, name FROM mcp_tools")}
    emp_skills = {}
    for es in _query_rows("SELECT employee_id, skill_id FROM employee_skills"):
        emp_skills.setdefault(es["employee_id"], []).append(es["skill_id"])
    # 智能体绑定知识库（真实多对多关系 → 展示名）
    emp_kb_names = {}
    for ek in _query_rows(
            "SELECT ek.employee_id, k.name FROM employee_kb ek "
            "JOIN knowledge_bases k ON k.id = ek.kb_id"):
        emp_kb_names.setdefault(ek["employee_id"], []).append(ek["name"])
    skill_mcp = {}
    for sm in _query_rows("SELECT skill_id, mcp_id FROM skill_mcp"):
        skill_mcp.setdefault(sm["skill_id"], []).append(sm["mcp_id"])
    # 活跃告警：按 target=emp_id 或 target_name=name 双匹配
    alert_by_target = {}
    alert_by_name = {}
    for a in _query_rows("SELECT target, target_name FROM alerts WHERE status='firing'"):
        if a.get("target"):
            alert_by_target[a["target"]] = alert_by_target.get(a["target"], 0) + 1
        if a.get("target_name"):
            alert_by_name[a["target_name"]] = alert_by_name.get(a["target_name"], 0) + 1

    # 从消息中提取每个智能体涉及的会话
    conv_by_route = {}
    msg_count_by_route = {}
    est_by_route = {}
    last_by_route = {}
    for m in msgs:
        r = _parse_route(m["route"])
        if not r:
            continue
        conv_by_route.setdefault(r, set()).add(m["conversation_id"])
        msg_count_by_route[r] = msg_count_by_route.get(r, 0) + 1
        if m["role"] == "user":
            est_by_route[r] = est_by_route.get(r, 0) + _est_tokens(m["content"])
        if m["created_at"]:
            last_by_route[r] = max(last_by_route.get(r, ""), m["created_at"])

    # 从 llm_calls 聚合真实 token
    today = datetime.now().strftime("%Y-%m-%d")
    call_stat = {}
    for c in calls:
        k = c["employee_id"]
        s = call_stat.setdefault(k, {"call_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                     "total_tokens": 0, "latency_sum": 0, "conv_ids": set(),
                                     "error_count": 0, "today_call_count": 0, "last_time": ""})
        s["call_count"] += 1
        s["prompt_tokens"] += c["prompt_tokens"] or 0
        s["completion_tokens"] += c["completion_tokens"] or 0
        s["total_tokens"] += c["total_tokens"] or 0
        s["latency_sum"] += c["latency_ms"] or 0
        if c.get("error"):
            s["error_count"] += 1
        if (c["created_at"] or "").startswith(today):
            s["today_call_count"] += 1
        if c["created_at"]:
            s["last_time"] = max(s["last_time"], c["created_at"])
        if c["conversation_id"]:
            s["conv_ids"].add(c["conversation_id"])

    result = []
    for a in agents:
        aid = a["id"]
        cs = call_stat.get(aid, {})
        conv_ids = conv_by_route.get(aid, set()) | cs.get("conv_ids", set())
        # 能力配置：关联技能 + 经 skill_mcp 展开的 MCP 工具
        skill_ids = emp_skills.get(aid, [])
        mcp_ids = set()
        for sid in skill_ids:
            mcp_ids.update(skill_mcp.get(sid, []))
        result.append({
            "id": aid, "name": a["name"], "type": a["type"], "model": a["model"] or "",
            "desc": a["desc"],
            "enabled": bool(a.get("enabled", 1)),
            "created": a.get("created", ""), "updated": a.get("updated", ""),
            "rag_kb": ", ".join(emp_kb_names.get(aid, [])) or a.get("rag_kb", ""),
            "prompt": _text_summary(a.get("prompt", ""), 200),
            "skills": [{"id": sid, "name": skill_map.get(sid, {}).get("name", sid),
                        "category": skill_map.get(sid, {}).get("category", "")}
                       for sid in skill_ids if sid in skill_map],
            "mcp_tools": [{"id": mid, "name": tool_map.get(mid, {}).get("name", mid)}
                          for mid in sorted(mcp_ids) if mid in tool_map],
            "conversation_count": len(conv_ids),
            "message_count": msg_count_by_route.get(aid, 0),
            "call_count": cs.get("call_count", 0),
            "prompt_tokens": cs.get("prompt_tokens", 0),
            "completion_tokens": cs.get("completion_tokens", 0),
            "total_tokens": cs.get("total_tokens", 0),
            "est_tokens": est_by_route.get(aid, 0),
            "error_count": cs.get("error_count", 0),
            "avg_latency_ms": round(cs.get("latency_sum", 0) / cs["call_count"], 1) if cs.get("call_count") else 0,
            "today_call_count": cs.get("today_call_count", 0),
            "active_alerts": alert_by_target.get(aid, 0) + alert_by_name.get(a["name"], 0),
            "last_active": max(last_by_route.get(aid, ""), cs.get("last_time", "")),
            "is_internal": False,
        })
    # 补充 llm_calls 中出现但不在 employees 表的实体（如"意图路由"），保留给总览表格/拓扑
    known = {a["id"] for a in agents}
    name_map = _agent_name_map()
    for eid, cs in call_stat.items():
        if eid and eid not in known:
            result.append({
                "id": eid, "name": name_map.get(eid, eid or "未知"), "type": "内部", "model": "",
                "desc": "路由/编排内部调用",
                "enabled": True,
                "created": "", "updated": "",
                "rag_kb": "", "prompt": "",
                "skills": [], "mcp_tools": [],
                "conversation_count": len(cs["conv_ids"]),
                "message_count": 0,
                "call_count": cs["call_count"],
                "prompt_tokens": cs["prompt_tokens"],
                "completion_tokens": cs["completion_tokens"],
                "total_tokens": cs["total_tokens"],
                "est_tokens": 0,
                "error_count": cs.get("error_count", 0),
                "avg_latency_ms": round(cs["latency_sum"] / cs["call_count"], 1) if cs["call_count"] else 0,
                "today_call_count": cs.get("today_call_count", 0),
                "active_alerts": 0,
                "last_active": cs.get("last_time", ""),
                "is_internal": True,
            })
    result.sort(key=lambda x: x["total_tokens"] + x["est_tokens"], reverse=True)
    return JSONResponse({"ok": True, "data": result})


@router.get("/api/monitor/conversations")
async def monitor_conversations():
    """会话列表：标题 / 关联智能体 / 输入输出摘要 / Token 汇总 / 时间"""
    convs = _query_rows("SELECT * FROM conversations ORDER BY updated_at DESC")
    msgs = _query_rows("SELECT conversation_id, role, content, conclusion, route, created_at FROM messages ORDER BY created_at")
    calls = _query_rows("SELECT conversation_id, total_tokens, prompt_tokens, completion_tokens FROM llm_calls")
    name_map = _agent_name_map()

    conv_msgs = {}
    for m in msgs:
        conv_msgs.setdefault(m["conversation_id"], []).append(m)
    call_by_conv = {}
    for c in calls:
        s = call_by_conv.setdefault(c["conversation_id"],
                                    {"count": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        s["count"] += 1
        s["prompt_tokens"] += c["prompt_tokens"] or 0
        s["completion_tokens"] += c["completion_tokens"] or 0
        s["total_tokens"] += c["total_tokens"] or 0

    result = []
    for cv in convs:
        cid = cv["id"]
        ms = conv_msgs.get(cid, [])
        user_msgs = [m for m in ms if m["role"] == "user"]
        agent_msgs = [m for m in ms if m["role"] == "agent"]
        routes = []
        for m in ms:
            r = _parse_route(m["route"])
            if r and r not in routes:
                routes.append(r)
        est = sum(_est_tokens(m["content"]) for m in ms)
        cs = call_by_conv.get(cid, {"count": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        result.append({
            "id": cid,
            "title": cv["title"],
            "created_at": cv["created_at"],
            "updated_at": cv["updated_at"],
            "message_count": len(ms),
            "user_input": _text_summary(user_msgs[-1]["content"] if user_msgs else ""),
            "agent_output": _text_summary(agent_msgs[-1]["conclusion"] if agent_msgs else ""),
            "agents": [{"id": r, "name": name_map.get(r, r)} for r in routes],
            "llm_call_count": cs["count"],
            "prompt_tokens": cs["prompt_tokens"],
            "completion_tokens": cs["completion_tokens"],
            "total_tokens": cs["total_tokens"],
            "est_tokens": est,
        })
    return JSONResponse({"ok": True, "data": result})


@router.get("/api/monitor/conversations/{conv_id}")
async def monitor_conversation_detail(conv_id: str):
    """会话详情：完整消息时间线 + 每次 LLM 调用的 Token/耗时明细"""
    conv = _query_rows("SELECT * FROM conversations WHERE id=?", (conv_id,))
    msgs = _query_rows("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at, id", (conv_id,))
    calls = _query_rows("SELECT * FROM llm_calls WHERE conversation_id=? ORDER BY created_at, id", (conv_id,))
    if not conv and not msgs and not calls:
        return JSONResponse({"ok": False, "error": "会话不存在"})
    return JSONResponse({"ok": True, "data": {
        "conversation": conv[0] if conv else {"id": conv_id, "title": "(无标题)", "created_at": "", "updated_at": ""},
        "messages": msgs,
        "llm_calls": calls,
    }})


@router.get("/api/monitor/timeseries")
async def monitor_timeseries(days: int = Query(7, ge=1, le=90)):
    """按天聚合的 LLM 调用量 / Token 趋势（近 N 天）"""
    calls = _query_rows("SELECT created_at, total_tokens, prompt_tokens, completion_tokens FROM llm_calls")
    msgs = _query_rows("SELECT created_at, content FROM messages")

    days_map = {}
    for i in range(days - 1, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        days_map[d] = {"call_count": 0, "total_tokens": 0, "message_count": 0, "est_tokens": 0}
    for c in calls:
        d = (c["created_at"] or "")[:10]
        if d in days_map:
            days_map[d]["call_count"] += 1
            days_map[d]["total_tokens"] += c["total_tokens"] or 0
    for m in msgs:
        d = (m["created_at"] or "")[:10]
        if d in days_map:
            days_map[d]["message_count"] += 1
            days_map[d]["est_tokens"] += _est_tokens(m["content"])

    series = [{"date": d, **v} for d, v in days_map.items()]
    return JSONResponse({"ok": True, "data": series})


@router.get("/api/monitor/token-dist")
async def monitor_token_dist():
    """Token 用量按智能体分布（饼图数据）"""
    calls = _query_rows("SELECT employee_id, employee_name, total_tokens FROM llm_calls")
    name_map = _agent_name_map()
    dist = {}
    for c in calls:
        k = c["employee_id"] or "unknown"
        name = c["employee_name"] or name_map.get(k, k or "未知")
        dist.setdefault(name, {"tokens": 0, "calls": 0})
        dist[name]["tokens"] += c["total_tokens"] or 0
        dist[name]["calls"] += 1
    data = [{"name": k, "value": v["tokens"], "calls": v["calls"]} for k, v in sorted(dist.items(), key=lambda x: -x[1]["tokens"])]
    return JSONResponse({"ok": True, "data": data})


@router.get("/api/monitor/topology")
async def monitor_topology():
    """智能体 APM 拓扑：总智能体(编排中枢) → 子智能体 → Skill → Tools → MCP Server 依赖链，
    以及 RAG 检索链路 数字员工 → 知识库 → 向量数据库。
    节点携带动态指标（调用数/Token/错误数），边携带关系类型（route / skill / tool / server / kb / vector）"""
    employees = _query_rows("SELECT id, name, type FROM employees")
    skills = _query_rows("SELECT id, name, category FROM skills")
    tools = _query_rows("SELECT id, name, category, server_id FROM mcp_tools")
    servers = _query_rows("SELECT id, name, desc, base_url FROM mcp_servers")
    emp_skills = _query_rows("SELECT employee_id, skill_id FROM employee_skills")
    skill_mcp = _query_rows("SELECT skill_id, mcp_id FROM skill_mcp")
    calls = _query_rows("SELECT employee_id, employee_name, total_tokens, latency_ms, error FROM llm_calls")
    # RAG 链路：知识库实体 / 员工↔知识库绑定 / 检索记录（rag_retrievals 无 kb_id，按员工绑定近似归属）
    kbs = _query_rows("SELECT id, name, description, doc_count, chunk_count FROM knowledge_bases")
    emp_kb = _query_rows("SELECT employee_id, kb_id FROM employee_kb")
    rags = _query_rows("SELECT employee_id FROM rag_retrievals")

    # 按智能体聚合动态指标（意图路由的调用 employee_id 为空，归到中枢节点）
    emp_stat = {}
    hub_stat = {"calls": 0, "tokens": 0, "errors": 0, "latency_sum": 0}
    for c in calls:
        s = emp_stat.setdefault(c["employee_id"] or "hub", {"calls": 0, "tokens": 0, "errors": 0, "latency_sum": 0})
        s["calls"] += 1
        s["tokens"] += c["total_tokens"] or 0
        s["latency_sum"] += c["latency_ms"] or 0
        if c.get("error"):
            s["errors"] += 1

    nodes = []
    hub = hub_stat
    nodes.append({
        "id": "hub", "name": "NeuOps 总智能体", "type": "hub", "subtype": "编排中枢",
        "desc": "意图路由与任务编排", "calls": hub["calls"], "tokens": hub["tokens"],
        "errors": hub["errors"],
        "avg_latency_ms": round(hub["latency_sum"] / hub["calls"], 1) if hub["calls"] else 0,
    })
    for e in employees:
        s = emp_stat.get(e["id"], {"calls": 0, "tokens": 0, "errors": 0, "latency_sum": 0})
        nodes.append({
            "id": e["id"], "name": e["name"], "type": "agent", "subtype": e["type"],
            "desc": "数字员工/子智能体", "calls": s["calls"], "tokens": s["tokens"],
            "errors": s["errors"],
            "avg_latency_ms": round(s["latency_sum"] / s["calls"], 1) if s["calls"] else 0,
        })
    for s in skills:
        nodes.append({"id": s["id"], "name": s["name"], "type": "skill", "subtype": s["category"],
                      "desc": "技能/知识包", "calls": 0, "tokens": 0, "errors": 0, "avg_latency_ms": 0})
    for t in tools:
        nodes.append({"id": t["id"], "name": t["name"], "type": "tool", "subtype": t["category"],
                      "desc": "MCP 工具", "calls": 0, "tokens": 0, "errors": 0, "avg_latency_ms": 0})
    for srv in servers:
        tool_count = sum(1 for t in tools if t.get("server_id") == srv["id"])
        nodes.append({"id": srv["id"], "name": srv["name"], "type": "server", "subtype": "服务",
                      "desc": srv.get("desc") or "MCP Server", "base_url": srv.get("base_url", ""),
                      "tool_count": tool_count, "calls": 0, "tokens": 0, "errors": 0, "avg_latency_ms": 0})

    edges = []
    for e in employees:
        edges.append({"source": "hub", "target": e["id"], "type": "route", "label": "路由"})
    for es in emp_skills:
        edges.append({"source": es["employee_id"], "target": es["skill_id"], "type": "skill", "label": "使用"})
    for sm in skill_mcp:
        edges.append({"source": sm["skill_id"], "target": sm["mcp_id"], "type": "tool", "label": "调用"})
    for t in tools:
        if t.get("server_id"):
            edges.append({"source": t["id"], "target": t["server_id"], "type": "server", "label": "归属"})

    # ── RAG 链路：数字员工 → 知识库 → 向量数据库（无知识库时不渲染，保持空数据兼容）──
    if kbs:
        # 检索次数聚合：员工 → 检索次数；知识库 → 绑定该库员工的检索次数之和
        # （rag_retrievals 无 kb_id 字段，员工绑定多库时次数计入其绑定库，近似口径）
        rag_by_emp = {}
        for r in rags:
            eid = r.get("employee_id") or ""
            if eid:
                rag_by_emp[eid] = rag_by_emp.get(eid, 0) + 1
        kb_retrieve = {}
        for ek in emp_kb:
            kb_retrieve[ek["kb_id"]] = kb_retrieve.get(ek["kb_id"], 0) + rag_by_emp.get(ek["employee_id"], 0)

        emp_ids = {e["id"] for e in employees}
        for k in kbs:
            nodes.append({
                "id": k["id"], "name": k["name"], "type": "kb", "subtype": "知识库",
                "desc": k.get("description") or "RAG 知识库",
                "doc_count": k.get("doc_count") or 0, "chunk_count": k.get("chunk_count") or 0,
                "retrieve_count": kb_retrieve.get(k["id"], 0),
                "calls": 0, "tokens": 0, "errors": 0, "avg_latency_ms": 0,
            })
            # 知识库 → 向量数据库（存储）
            edges.append({"source": k["id"], "target": "chroma", "type": "vector", "label": "存储"})
        # 数字员工 → 知识库（检索，基于 employee_kb 绑定）
        for ek in emp_kb:
            if ek["employee_id"] in emp_ids:
                edges.append({"source": ek["employee_id"], "target": ek["kb_id"], "type": "kb", "label": "检索"})

        # 全局唯一向量数据库节点
        chunk_row = _query_rows("SELECT COUNT(*) AS n FROM knowledge_chunks")
        total_chunks = chunk_row[0]["n"] if chunk_row else 0
        nodes.append({
            "id": "chroma", "name": "ChromaDB 向量库", "type": "vector_db", "subtype": "向量数据库",
            "desc": f"collection: knowledge_chunks | 模型: {EMBED_MODEL}",
            "collection": "knowledge_chunks", "model": EMBED_MODEL,
            "total_chunks": total_chunks, "retrieve_count": sum(rag_by_emp.values()),
            "calls": 0, "tokens": 0, "errors": 0, "avg_latency_ms": 0,
        })

    return JSONResponse({"ok": True, "data": {"nodes": nodes, "edges": edges}})


@router.get("/api/monitor/alerts")
async def monitor_alerts(status: str = "firing", limit: int = Query(100, ge=1, le=500)):
    """告警中心：按状态筛选告警记录（firing 未恢复 / resolved 已恢复 / all 全部）"""
    if status not in ("firing", "resolved", "all"):
        status = "all"
    if status == "all":
        rows = _query_rows("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,))
    else:
        rows = _query_rows("SELECT * FROM alerts WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
    return JSONResponse({"ok": True, "data": rows})


@router.get("/api/monitor/alert-rules")
async def monitor_alert_rules():
    """告警规则列表（含当前未恢复告警数），支持启用/停用"""
    rules = _query_rows("SELECT * FROM alert_rules ORDER BY id")
    firing = {}
    for a in _query_rows("SELECT rule_id FROM alerts WHERE status='firing'"):
        firing[a["rule_id"]] = firing.get(a["rule_id"], 0) + 1
    for r in rules:
        r["firing_count"] = firing.get(r["id"], 0)
    return JSONResponse({"ok": True, "data": rules})


@router.post("/api/monitor/alert-rules/{rid}/toggle")
async def monitor_alert_rule_toggle(rid: str):
    """启用/停用告警规则"""
    rules = _query_rows("SELECT id, enabled FROM alert_rules WHERE id=?", (rid,))
    if not rules:
        return JSONResponse({"ok": False, "error": "规则不存在"})
    new_enabled = 0 if rules[0]["enabled"] else 1
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("UPDATE alert_rules SET enabled=? WHERE id=?", (new_enabled, rid))
            conn.commit()
        finally:
            conn.close()
    return JSONResponse({"ok": True, "data": {"id": rid, "enabled": new_enabled}})


@router.post("/api/monitor/agents/{emp_id}/toggle")
async def monitor_agent_toggle(emp_id: str):
    """开启/关闭数字员工（仅监控页状态展示，不影响主应用意图路由）"""
    agents = _query_rows("SELECT id, enabled FROM employees WHERE id=?", (emp_id,))
    if not agents:
        return JSONResponse({"ok": False, "error": "智能体不存在"}, status_code=404)
    new_enabled = 0 if agents[0]["enabled"] else 1
    db_set_employee_enabled(emp_id, bool(new_enabled))
    return JSONResponse({"ok": True, "data": {"id": emp_id, "enabled": new_enabled}})


@router.get("/api/monitor/agents/{emp_id}/full")
async def monitor_agent_full(emp_id: str):
    """智能体详情抽屉数据：完整信息 + 技能/MCP 工具详情 + 监控指标 + 最近会话 + 链路追踪 + 告警"""
    emp = db_get_employee(emp_id)
    if not emp:
        return JSONResponse({"ok": False, "error": "智能体不存在"}, status_code=404)

    # 技能详情（含 desc / category / enabled）
    all_skills = _query_rows("SELECT * FROM skills")
    skill_map = {s["id"]: s for s in all_skills}
    skill_details = []
    for sid in emp.get("skills", []):
        s = skill_map.get(sid)
        if s:
            s = dict(s)
            s["enabled"] = bool(s.get("enabled"))
            skill_details.append(s)

    # MCP 工具详情
    all_tools = {t["id"]: t for t in _query_rows("SELECT * FROM mcp_tools")}
    mcp_detail = [dict(all_tools[mid]) for mid in emp.get("mcp_tools", []) if mid in all_tools]

    # 该智能体的消息 / 调用
    calls = _query_rows("SELECT * FROM llm_calls WHERE employee_id=?", (emp_id,))
    msgs = _query_rows("SELECT conversation_id, route, content, role, created_at FROM messages")

    # 监控指标
    today = datetime.now().strftime("%Y-%m-%d")
    conv_by_route = set()
    msg_count = 0
    est = 0
    last_active = ""
    for m in msgs:
        if _parse_route(m["route"]) != emp_id:
            continue
        conv_by_route.add(m["conversation_id"])
        msg_count += 1
        if m["role"] == "user":
            est += _est_tokens(m["content"])
        if m["created_at"]:
            last_active = max(last_active, m["created_at"])

    conv_ids = set(conv_by_route)
    err = lat_sum = tk_p = tk_c = tk_t = 0
    today_calls = 0
    for c in calls:
        if c["conversation_id"]:
            conv_ids.add(c["conversation_id"])
        if c.get("error"):
            err += 1
        lat_sum += c["latency_ms"] or 0
        tk_p += c["prompt_tokens"] or 0
        tk_c += c["completion_tokens"] or 0
        tk_t += c["total_tokens"] or 0
        if (c["created_at"] or "").startswith(today):
            today_calls += 1
        if c["created_at"]:
            last_active = max(last_active, c["created_at"])
    metrics = {
        "conversation_count": len(conv_ids),
        "message_count": msg_count,
        "call_count": len(calls),
        "prompt_tokens": tk_p, "completion_tokens": tk_c, "total_tokens": tk_t,
        "est_tokens": est,
        "error_count": err,
        "avg_latency_ms": round(lat_sum / len(calls), 1) if calls else 0,
        "today_call_count": today_calls,
        "last_active": last_active,
    }

    # 最近会话（按该智能体涉及的会话聚合，取最新 5 条）
    recent_convs = []
    if conv_ids:
        ph = ",".join("?" * len(conv_ids))
        conv_rows = _query_rows(
            f"SELECT id, title, created_at, updated_at FROM conversations WHERE id IN ({ph})",
            tuple(conv_ids))
        msg_by_conv = {}
        for m in msgs:
            if m["conversation_id"] in conv_ids:
                msg_by_conv[m["conversation_id"]] = msg_by_conv.get(m["conversation_id"], 0) + 1
        call_by_conv = {}
        for c in calls:
            s = call_by_conv.setdefault(c["conversation_id"],
                                        {"count": 0, "total_tokens": 0, "error_count": 0})
            s["count"] += 1
            s["total_tokens"] += c["total_tokens"] or 0
            if c.get("error"):
                s["error_count"] += 1
        for cv in conv_rows:
            cs = call_by_conv.get(cv["id"], {})
            recent_convs.append({
                "id": cv["id"], "title": cv["title"],
                "created_at": cv["created_at"], "updated_at": cv["updated_at"],
                "message_count": msg_by_conv.get(cv["id"], 0),
                "llm_call_count": cs.get("count", 0),
                "total_tokens": cs.get("total_tokens", 0),
                "error_count": cs.get("error_count", 0),
            })
        recent_convs.sort(key=lambda x: x["updated_at"] or "", reverse=True)
        recent_convs = recent_convs[:5]

    # 相关链路追踪：llm_calls 按 conversation_id 分组（APM 语义：Trace = 会话，Span = 调用）
    trace_groups = {}
    for c in calls:
        trace_groups.setdefault(c["conversation_id"], []).append(c)
    conv_title = {c["id"]: c["title"] for c in _query_rows("SELECT id, title FROM conversations")}
    traces = []
    for cid, spans in trace_groups.items():
        spans_sorted = sorted(spans, key=lambda x: x["created_at"] or "")
        traces.append({
            "conversation_id": cid,
            "title": conv_title.get(cid, cid),
            "start": spans_sorted[0]["created_at"],
            "end": spans_sorted[-1]["created_at"],
            "span_count": len(spans_sorted),
            "total_latency_ms": sum(s["latency_ms"] or 0 for s in spans_sorted),
            "total_tokens": sum(s["total_tokens"] or 0 for s in spans_sorted),
            "error_count": sum(1 for s in spans_sorted if s["error"]),
        })
    traces.sort(key=lambda x: x["start"] or "", reverse=True)
    traces = traces[:5]

    # 相关告警：target=emp_id 或 target_name=name
    alerts = _query_rows(
        "SELECT id, rule_name, severity, metric, status, message, value, created_at "
        "FROM alerts WHERE (target=? OR target_name=?) ORDER BY created_at DESC LIMIT 5",
        (emp_id, emp["name"]))

    return JSONResponse({"ok": True, "data": {
        "employee": {
            "id": emp["id"], "name": emp["name"], "desc": emp["desc"] or "",
            "type": emp["type"] or "", "model": emp["model"] or "",
            "rag_kb": emp["rag_kb"] or "", "prompt": emp["prompt"] or "",
            "created": emp["created"] or "", "updated": emp["updated"] or "",
            "enabled": bool(emp.get("enabled", 1)),
        },
        "skill_details": skill_details,
        "mcp_detail": mcp_detail,
        "metrics": metrics,
        "recent_conversations": recent_convs,
        "traces": traces,
        "alerts": alerts,
    }})


@router.get("/api/monitor/traces")
async def monitor_traces(limit: int = Query(50, ge=1, le=200)):
    """链路追踪列表：一个会话 = 一条 Trace，每次 LLM 调用 = 一个 Span（APM 语义）"""
    calls = _query_rows("SELECT * FROM llm_calls ORDER BY created_at DESC")
    conv_title = {c["id"]: c["title"] for c in _query_rows("SELECT id, title FROM conversations")}
    groups = {}
    for c in calls:
        groups.setdefault(c["conversation_id"], []).append(c)
    result = []
    for cid, spans in groups.items():
        spans_sorted = sorted(spans, key=lambda x: x["created_at"])
        agents = []
        for s in spans_sorted:
            nm = s["employee_name"] or s["employee_id"] or "意图路由"
            if nm and nm not in agents:
                agents.append(nm)
        result.append({
            "conversation_id": cid,
            "title": conv_title.get(cid, cid),
            "start": spans_sorted[0]["created_at"],
            "end": spans_sorted[-1]["created_at"],
            "span_count": len(spans_sorted),
            "total_tokens": sum(s["total_tokens"] or 0 for s in spans_sorted),
            "total_latency_ms": sum(s["latency_ms"] or 0 for s in spans_sorted),
            "error_count": sum(1 for s in spans_sorted if s["error"]),
            "agents": agents,
        })
    result.sort(key=lambda x: x["start"], reverse=True)
    return JSONResponse({"ok": True, "data": result[:limit]})


# 工具函数白名单（真实系统/接口/代码数据），其余走 mcp mock 网关的视为演示数据
_REAL_TOOL_FNS = {
    # 9006 经营分析系统
    "list_tables", "get_table_schema", "query_table", "get_metrics", "get_etl_metrics",
    "query_contracts", "query_ontology", "get_comparison_results", "get_contract_comparison",
    # 研发协作（代码/文件/命令，真实文件系统）
    "list_project_files", "search_code", "read_code_file", "write_new_file", "edit_code_file", "run_shell",
}


def _tool_data_source(fn: str, result: str) -> str:
    """判断工具调用数据来源：real（真实系统/接口调用）/ mock（演示数据）/ unknown"""
    # 真实系统接口调用优先：即使沙箱返回模拟数据，调用链本身是真实的
    if fn in _REAL_TOOL_FNS:
        return "real"
    try:
        obj = json.loads(result or "{}")
        if isinstance(obj, dict) and isinstance(obj.get("data_source"), str):
            ds = obj["data_source"].lower()
            if ds in ("real", "live", "true"):
                return "real"
            if ds in ("mock", "sim", "demo"):
                return "mock"
    except Exception:
        pass
    # mcp_gateway 的 mock 工具（告警/巡检/变更/CMDB 等均为演示数据）
    if fn.startswith(("tool_", "get_business", "search_", "query_cmdb", "query_change", "query_alarm",
                      "run_auto", "query_container", "scan_", "verify_")):
        return "mock"
    return "unknown"


@router.get("/api/monitor/traces/{conv_id}")
async def monitor_trace_detail(conv_id: str):
    """单条 Trace 详情：Span 全字段 + 工具调用 + RAG 检索 + 会话消息 + 聚合统计（APM 语义）"""
    spans = _query_rows("SELECT * FROM llm_calls WHERE conversation_id=? ORDER BY created_at, id", (conv_id,))
    tool_calls = _query_rows("SELECT * FROM tool_calls WHERE conversation_id=? ORDER BY created_at, id", (conv_id,))
    rag_calls = _query_rows("SELECT * FROM rag_retrievals WHERE conversation_id=? ORDER BY created_at, id", (conv_id,))
    msgs = _query_rows(
        "SELECT id, role, content, thought, tools, conclusion, route, created_at "
        "FROM messages WHERE conversation_id=? ORDER BY created_at, id", (conv_id,))
    conv = _query_rows("SELECT id, title, created_at FROM conversations WHERE id=?", (conv_id,))
    # 数据来源标注：工具按函数名/返回值判断；消息按会话是否有真实 LLM 调用判断
    has_real_llm = bool(spans)
    for t in tool_calls:
        t["data_source"] = _tool_data_source(t.get("function_name") or "", t.get("result") or "")
    for m in msgs:
        if m.get("role") == "user":
            m["source"] = "user"
        else:
            m["source"] = "llm_real" if has_real_llm else "seed"
    src_stats = {"real": 0, "mock": 0, "unknown": 0}
    for t in tool_calls:
        src_stats[t.get("data_source", "unknown")] = src_stats.get(t.get("data_source", "unknown"), 0) + 1

    # 聚合统计
    total_latency = sum(s["latency_ms"] or 0 for s in spans)
    total_tokens = sum(s["total_tokens"] or 0 for s in spans)
    cost = round(sum(s["cost"] or 0 for s in spans), 6)
    if cost <= 0:
        cost = round(sum((s["prompt_tokens"] or 0) / 1e6 * _COST_INPUT_PER_M
                         + (s["completion_tokens"] or 0) / 1e6 * _COST_OUTPUT_PER_M for s in spans), 6)
    error_count = sum(1 for s in spans if s["error"])
    slowest = None
    for s in spans:
        if (s["latency_ms"] or 0) > (slowest["latency_ms"] or 0 if slowest else 0):
            slowest = s
    # 阶段耗时占比（路由蓝 / 执行青 / 兜底紫）
    stage_ratio = {"intent_route": 0, "agent_exec": 0, "agent_exec_fallback": 0, "other": 0}
    for s in spans:
        st = s["stage"] or "other"
        stage_ratio[st if st in stage_ratio else "other"] += s["latency_ms"] or 0
    total_stage = sum(stage_ratio.values()) or 1
    for k in stage_ratio:
        stage_ratio[k] = round(stage_ratio[k] / total_stage * 100, 1)

    return JSONResponse({"ok": True, "data": {
        "conversation": conv[0] if conv else {"id": conv_id, "title": conv_id, "created_at": ""},
        "spans": spans,
        "tool_calls": tool_calls,
        "rag_calls": rag_calls,
        "messages": msgs,
        "source_stats": {
            "llm_calls": len(spans),
            "tool_calls": src_stats,
            "rag_calls": len(rag_calls),
        },
        "stats": {
            "status": "error" if error_count else "success",
            "error_count": error_count,
            "total_latency_ms": total_latency,
            "total_tokens": total_tokens,
            "cost": cost,
            "stage_ratio": stage_ratio,
            "slowest_span": slowest,
        },
    }})


@router.get("/api/monitor/slow-calls")
async def monitor_slow_calls(threshold_ms: int = Query(10000, ge=0), limit: int = Query(50, ge=1, le=200)):
    """慢调用列表（对应传统 APM 的慢 SQL / 慢事务）：按耗时倒序"""
    calls = _query_rows(
        "SELECT * FROM llm_calls WHERE latency_ms >= ? ORDER BY latency_ms DESC LIMIT ?",
        (threshold_ms, limit))
    name_map = _agent_name_map()
    for c in calls:
        c["employee_name"] = c["employee_name"] or name_map.get(c["employee_id"], c["employee_id"] or "意图路由")
    return JSONResponse({"ok": True, "data": calls})


@router.get("/monitor")
async def monitor_page():
    """保留旧 URL 兼容：重定向到一体化监控平台 /ops"""
    return RedirectResponse(url="/ops", status_code=302)
