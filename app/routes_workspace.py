"""会话 / 技能 / 知识库等工作区路由"""

import json
import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from seed_data import MOCK_CONV_MESSAGES

from .db import (
    _db_lock,
    _get_conn,
    db_create_project,
    db_delete_conversation,
    db_delete_mcp_server,
    db_delete_project,
    db_delete_skill,
    db_get_conv_by_share,
    db_get_conversation_share,
    db_get_employee_kb_ids,
    db_get_mcp_server,
    db_get_skill,
    db_list_bg_tasks,
    db_list_knowledge_bases,
    db_list_mcp_servers,
    db_list_mcp_tools,
    db_list_projects,
    db_list_skills,
    db_mark_mock_conv_deleted,
    db_rename_project,
    db_set_skill_enabled,
    db_share_conversation,
    db_sync_server_tools,
    db_update_conversation,
    db_update_mcp_tool,
    db_upsert_mcp_server,
    db_upsert_skill,
    get_conversation_messages,
    list_conversations,
)
from .knowledge import search_knowledge

router = APIRouter()


@router.post("/api/conversations")
async def create_conversation():
    """新建会话，返回会话 ID"""
    conv_id = "conv-" + str(uuid.uuid4())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, '新对话', ?, ?)",
                (conv_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    return JSONResponse({"conversation_id": conv_id})


@router.get("/api/skills")
async def get_skills():
    skills = db_list_skills()
    # 返回兼容前端的字段（id/name/desc/category/tags/enabled/group）
    return JSONResponse({"skills": [
        {"id": s["id"], "name": s["name"], "desc": s["desc"], "category": s["category"],
         "tags": s.get("tags", []), "enabled": s.get("enabled", True), "group": s.get("group", "")}
        for s in skills
    ]})


@router.post("/api/skills/toggle")
async def toggle_skill(req: Request):
    body = await req.json()
    skill_id = body.get("skill_id")
    enabled = body.get("enabled")
    skill = db_get_skill(skill_id)
    if not skill:
        return JSONResponse({"success": False, "error": "Skill not found"}, status_code=404)
    db_set_skill_enabled(skill_id, bool(enabled))
    skill["enabled"] = bool(enabled)
    return JSONResponse({"success": True, "skill": skill})


@router.get("/api/conversations")
async def get_conversations():
    """从会话库读取会话列表"""
    convs = list_conversations()
    if convs:
        return JSONResponse({
            "conversations": [
                {
                    "id": c["id"],
                    "title": c["title"],
                    "created": c["created_at"],
                    "updated": c.get("updated_at", c["created_at"]),
                    "project_id": c.get("project_id", "") or "",
                    "pinned": bool(c.get("pinned", False)),
                    "share_id": c.get("share_id", "") or "",
                }
                for c in convs
            ]
        })
    # 会话库为空时返回预置 demo 会话
    return JSONResponse({
        "conversations": [
            {"id": "conv-demo-001", "title": "订单服务延迟故障排查", "group": "故障排查会话", "created": "2026-08-07 14:32", "pinned": True, "project_id": ""},
            {"id": "conv-demo-002", "title": "支付集群每日巡检", "group": "例行巡检会话", "created": "2026-08-07 09:00", "pinned": False, "project_id": ""},
            {"id": "conv-demo-003", "title": "数据库慢查询分析", "group": "故障排查会话", "created": "2026-08-06 16:20", "pinned": False, "project_id": ""},
        ]
    })


# ═══════════════════════════════════════════
# 项目 CRUD
# ═══════════════════════════════════════════

@router.get("/api/projects")
async def get_projects():
    projects = db_list_projects()
    return JSONResponse({"projects": projects})


@router.post("/api/projects")
async def create_project(req: Request):
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "项目名称不能为空"}, status_code=400)
    pid = db_create_project(name)
    return JSONResponse({"success": True, "project": {"id": pid, "name": name, "conv_count": 0}})


@router.patch("/api/projects/{project_id}")
async def rename_project(project_id: str, req: Request):
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "项目名称不能为空"}, status_code=400)
    if not db_rename_project(project_id, name):
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    return JSONResponse({"success": True})


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    db_delete_project(project_id)
    return JSONResponse({"success": True})


# ═══════════════════════════════════════════
# 会话操作：置顶 / 重命名 / 移动 / 删除 / 分享
# ═══════════════════════════════════════════

@router.patch("/api/conversations/{conv_id}")
async def update_conversation(conv_id: str, req: Request):
    """更新会话属性：title（重命名）/ project_id（移动项目）/ pinned（置顶）"""
    body = await req.json()
    fields = {}
    if "title" in body:
        title = (body.get("title") or "").strip()
        if not title:
            return JSONResponse({"success": False, "error": "标题不能为空"}, status_code=400)
        fields["title"] = title
    if "project_id" in body:
        fields["project_id"] = body.get("project_id") or ""
    if "pinned" in body:
        fields["pinned"] = 1 if body.get("pinned") else 0
    if not fields:
        return JSONResponse({"success": False, "error": "无可更新字段"}, status_code=400)
    if not db_update_conversation(conv_id, fields):
        return JSONResponse({"success": False, "error": "会话不存在"}, status_code=404)
    return JSONResponse({"success": True})


@router.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    db_delete_conversation(conv_id)
    # 数字员工详情里的预置 mock 会话不在库中，需持久化删除标记防止刷新后复活
    db_mark_mock_conv_deleted(conv_id)
    return JSONResponse({"success": True})


@router.post("/api/conversations/{conv_id}/share")
async def share_conversation(conv_id: str):
    share_id = db_share_conversation(conv_id)
    if not share_id:
        return JSONResponse({"success": False, "error": "会话不存在"}, status_code=404)
    return JSONResponse({"success": True, "share_id": share_id})


@router.get("/api/conversations/{conv_id}/share")
async def get_share_info(conv_id: str):
    share_id = db_get_conversation_share(conv_id)
    return JSONResponse({"success": True, "share_id": share_id})


@router.get("/api/share/{share_id}")
async def get_shared_conversation(share_id: str):
    """通过分享 ID 读取会话快照（只读）"""
    found = db_get_conv_by_share(share_id)
    if not found:
        return JSONResponse({"success": False, "error": "分享不存在或已失效"}, status_code=404)
    conv_id, title = found
    data = get_conversation_messages(conv_id)
    data["title"] = title
    return JSONResponse({"success": True, "conversation": data})


@router.get("/api/knowledge")
async def get_knowledge(query: str = "", employee_id: str = ""):
    """真实知识库检索：按员工绑定知识库 + 关键词查询返回相关片段

    兼容旧返回结构（recommendations[]），方便前端无改动接入。
    """
    kb_ids = []
    if employee_id:
        kb_ids = db_get_employee_kb_ids(employee_id)
    if not kb_ids:
        kb_ids = [k["id"] for k in db_list_knowledge_bases()]
    results = search_knowledge(query, kb_ids, top_k=5)
    return JSONResponse({"recommendations": results, "knowledge": results, "items": results})


@router.get("/api/bg-tasks")
async def get_bg_tasks():
    return JSONResponse({"tasks": db_list_bg_tasks()})


@router.get("/api/skills/{skill_id}/detail")
async def get_skill_detail(skill_id: str):
    """获取 Skill 详情，优先从 JSON 配置文件加载（热更新），降级到 DB。"""
    from app.skill_loader import load_skill
    from app.db.seed import db_list_mcp_tools

    # 1. 优先从 JSON 文件加载
    json_skill = load_skill(skill_id)
    if json_skill:
        sk = json_skill["skill"]
        # 工具 ID → 完整工具对象（前端期望 {name, desc} 格式）
        all_tools = {t["id"]: t for t in db_list_mcp_tools()}
        raw_tools = json_skill.get("tools", [])
        resolved_tools = []
        for t in raw_tools:
            if isinstance(t, dict):
                resolved_tools.append(t)
            elif isinstance(t, str) and t in all_tools:
                resolved_tools.append({
                    "id": all_tools[t]["id"],
                    "name": all_tools[t]["name"],
                    "desc": all_tools[t]["desc"],
                })
        return JSONResponse({
            "name": sk.get("name", skill_id),
            "desc": f"{sk.get('version', '')} {sk.get('trigger_intent', '')}".strip(),
            "type": sk.get("type", sk.get("skill_type", "")),
            "category": sk.get("category", ""),
            "tags": sk.get("tags", []),
            "prompt": json_skill["prompt"],
            "flow": sk.get("flow", f"状态机驱动，参考 {skill_id}.json"),
            "tools": resolved_tools,
            "source": json_skill["source"],
            "version": sk.get("version", ""),
            "skill_json": sk,  # 完整结构化定义，前端渲染用
            "is_structured": bool(sk.get("field_model")),  # 是否为 V2 结构化 Skill
        })

    # 2. 降级：从 DB 读取
    skill = db_get_skill(skill_id)
    if not skill:
        return JSONResponse({"error": "Skill not found"}, status_code=404)
    all_tools = {t["id"]: t for t in db_list_mcp_tools()}
    tools = [all_tools[mid] for mid in skill.get("mcp_tools", []) if mid in all_tools]
    return JSONResponse({
        "name": skill["name"],
        "desc": skill["desc"],
        "type": skill.get("skill_type", ""),
        "category": skill.get("category", ""),
        "tags": skill.get("tags", []),
        "prompt": skill.get("prompt", ""),
        "flow": skill.get("flow", ""),
        "tools": tools,
        "source": "db",
        "is_structured": False,
        "skill_json": {},
    })


@router.put("/api/skills/{skill_id}/json")
async def save_skill_json(skill_id: str, body: dict):
    """保存 Skill 的 JSON 结构化定义到配置文件（后台编辑用）。"""
    from app.skill_loader import save_skill_json as _save, clear_cache
    skill_def = body.get("skill_json") or body
    if not isinstance(skill_def, dict):
        return JSONResponse({"error": "skill_json 必须是对象"}, status_code=400)
    # 确保 skill_id 匹配
    if not skill_def.get("skill_id"):
        skill_def["skill_id"] = skill_id
    ok = _save(skill_id, skill_def)
    if ok:
        clear_cache(skill_id)
        return JSONResponse({"ok": True, "skill_id": skill_id, "version": skill_def.get("version", "")})
    return JSONResponse({"error": "保存失败"}, status_code=500)


@router.get("/api/skills/{skill_id}/json")
async def get_skill_json(skill_id: str):
    """获取 Skill 的 JSON 定义（后台编辑用）。"""
    from app.skill_loader import load_skill
    sk = load_skill(skill_id)
    if sk:
        return JSONResponse({"ok": True, "skill_json": sk["skill"], "source": sk.get("source", "")})
    return JSONResponse({"error": "Skill not found"}, status_code=404)


@router.get("/api/conversations/{conv_id}/messages")
async def get_conv_messages(conv_id: str):
    """从会话库读取完整消息历史"""
    data = get_conversation_messages(conv_id)
    if data["messages"]:
        return JSONResponse(data)
    # 会话库无此会话，回退到预置 mock（兼容旧预置会话）
    conv = MOCK_CONV_MESSAGES.get(conv_id)
    if conv:
        return JSONResponse({
            "conversation_id": conv_id,
            "title": conv.get("title", ""),
            "employee_id": conv.get("employee_id", ""),
            "messages": conv.get("messages", []),
        })
    return JSONResponse({"conversation_id": conv_id, "title": "新会话", "messages": []})

@router.get("/api/skills/full")
async def list_skills_full():
    """返回技能完整信息（含分类、标签、分组）"""
    skills = db_list_skills()
    return JSONResponse({"skills": [
        {"id": s["id"], "name": s["name"], "desc": s["desc"], "category": s["category"],
         "tags": s.get("tags", []), "enabled": s.get("enabled", True), "group": s.get("group", "")}
        for s in skills
    ]})


# ═══════════════════════════════════════════
# MCP Server / MCP 工具 管理
# ═══════════════════════════════════════════

@router.get("/api/mcp-servers")
async def get_mcp_servers():
    """MCP Server 列表（含各自工具数）"""
    return JSONResponse({"servers": db_list_mcp_servers()})


@router.post("/api/mcp-servers")
async def create_mcp_server(req: Request):
    """添加外部 MCP Server：name / base_url / type / auth / desc / id（可选，指定后可预置 neuops-local/mcp-gateway 等固定 ID）"""
    body = await req.json()
    name = (body.get("name") or "").strip()
    base_url = (body.get("base_url") or "").strip().rstrip("/")
    if not name or not base_url:
        return JSONResponse({"success": False, "error": "名称和 Base URL 不能为空"}, status_code=400)
    # 允许调用方显式指定 id（用于写入 neuops-local / mcp-gateway 等固定 server）
    server_id = (body.get("id") or "").strip() or "mcp-" + str(uuid.uuid4())[:8]
    server = {
        "id": server_id,
        "name": name,
        "desc": body.get("desc", ""),
        "base_url": base_url,
        "type": body.get("type", "gateway"),
        "auth": json.dumps(body.get("auth", {}), ensure_ascii=False) if isinstance(body.get("auth"), (dict, list)) else (body.get("auth") or ""),
        "group": body.get("group", ""),
        "status": body.get("status", "online"),
        "last_sync": body.get("last_sync", ""),
    }
    db_upsert_mcp_server(server)
    return JSONResponse({"success": True, "server": server})


@router.put("/api/mcp-servers/{server_id}")
async def update_mcp_server(server_id: str, req: Request):
    """编辑 MCP Server"""
    body = await req.json()
    existing = db_get_mcp_server(server_id)
    if not existing:
        return JSONResponse({"success": False, "error": "MCP Server 不存在"}, status_code=404)
    server = {
        "id": server_id,
        "name": (body.get("name") or existing["name"]).strip(),
        "desc": body.get("desc", existing.get("desc", "")),
        "base_url": (body.get("base_url") or existing["base_url"]).strip().rstrip("/"),
        "type": body.get("type", existing.get("type", "gateway")),
        "auth": json.dumps(body.get("auth", {}), ensure_ascii=False) if isinstance(body.get("auth"), (dict, list)) else (body.get("auth") or existing.get("auth", "")),
        "group": body.get("group", existing.get("group", "")),
        "status": body.get("status", existing.get("status", "online")),
        "last_sync": existing.get("last_sync", ""),
    }
    db_upsert_mcp_server(server)
    return JSONResponse({"success": True, "server": server})


@router.delete("/api/mcp-servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """删除 MCP Server（级联清理其下工具与技能绑定）"""
    if not db_get_mcp_server(server_id):
        return JSONResponse({"success": False, "error": "MCP Server 不存在"}, status_code=404)
    db_delete_mcp_server(server_id)
    return JSONResponse({"success": True})


@router.post("/api/mcp-servers/{server_id}/sync")
async def sync_mcp_server_tools(server_id: str):
    """同步工具：GET {base_url}/tools → 解析 → 入库"""
    server = db_get_mcp_server(server_id)
    if not server:
        return JSONResponse({"success": False, "error": "MCP Server 不存在"}, status_code=404)
    url = f"{server['base_url']}/tools"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        return JSONResponse({"success": False, "error": f"拉取工具列表失败: {e}"}, status_code=502)
    tools = payload.get("tools", payload if isinstance(payload, list) else [])
    count = db_sync_server_tools(server_id, tools)
    return JSONResponse({"success": True, "count": count, "server": db_get_mcp_server(server_id)})


@router.get("/api/mcp-tools")
async def get_mcp_tools(server_id: str = ""):
    """工具列表，可按 server_id 过滤"""
    tools = db_list_mcp_tools(server_id)
    return JSONResponse({"tools": tools})


@router.put("/api/mcp-tools/{tool_id}")
async def update_mcp_tool(tool_id: str, req: Request):
    """更新 MCP 工具字段（当前用于单独调整业务分组 group）"""
    body = await req.json()
    fields = {}
    for key in ("group", "name", "desc", "tag", "category"):
        if key in body:
            fields[key] = str(body[key] or "").strip()
    if not fields:
        return JSONResponse({"success": False, "error": "无可更新字段"}, status_code=400)
    if not db_update_mcp_tool(tool_id, fields):
        return JSONResponse({"success": False, "error": "工具不存在"}, status_code=404)
    return JSONResponse({"success": True})


# ═══════════════════════════════════════════
# 技能 CRUD（创建 / 编辑 / 删除，支持绑定工具）
# ═══════════════════════════════════════════

@router.post("/api/skills")
async def create_skill(req: Request):
    """新建技能：name / desc / category / prompt / flow / tools[]"""
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "技能名称不能为空"}, status_code=400)
    skill_id = "skill-" + str(uuid.uuid4())[:8]
    skill = {
        "id": skill_id,
        "name": name,
        "desc": body.get("desc", ""),
        "category": body.get("category", "自定义"),
        "group": body.get("group", ""),
        "tags": body.get("tags", ["自定义"]),
        "enabled": True,
        "prompt": body.get("prompt", ""),
        "flow": body.get("flow", ""),
        "skill_type": body.get("skill_type", "custom"),
    }
    tools = body.get("tools") or []
    # 校验工具存在
    all_tools = {t["id"] for t in db_list_mcp_tools()}
    valid_tools = [t for t in tools if t in all_tools]
    db_upsert_skill(skill, valid_tools)
    return JSONResponse({"success": True, "skill": skill})


@router.put("/api/skills/{skill_id}")
async def update_skill(skill_id: str, req: Request):
    """编辑技能（可调整绑定的 tools）"""
    body = await req.json()
    existing = db_get_skill(skill_id)
    if not existing:
        return JSONResponse({"success": False, "error": "技能不存在"}, status_code=404)
    skill = {
        "id": skill_id,
        "name": (body.get("name") or existing["name"]).strip(),
        "desc": body.get("desc", existing.get("desc", "")),
        "category": body.get("category", existing.get("category", "自定义")),
        "group": body.get("group", existing.get("group", "")),
        "tags": body.get("tags", existing.get("tags", ["自定义"])),
        "enabled": body.get("enabled", existing.get("enabled", True)),
        "prompt": body.get("prompt", existing.get("prompt", "")),
        "flow": body.get("flow", existing.get("flow", "")),
        "skill_type": body.get("skill_type", existing.get("skill_type", "")),
    }
    all_tools = {t["id"] for t in db_list_mcp_tools()}
    valid_tools = [t for t in (body.get("tools") or []) if t in all_tools]
    db_upsert_skill(skill, valid_tools)
    return JSONResponse({"success": True, "skill": skill})


@router.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """删除技能"""
    if not db_get_skill(skill_id):
        return JSONResponse({"success": False, "error": "技能不存在"}, status_code=404)
    db_delete_skill(skill_id)
    return JSONResponse({"success": True})
