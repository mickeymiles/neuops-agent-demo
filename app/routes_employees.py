"""数字员工 CRUD 路由"""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .db import (
    db_delete_employee,
    db_get_deleted_mock_convs,
    db_get_employee,
    db_link_employee_skills,
    db_list_employees,
    db_list_mcp_tools,
    db_list_skills,
    db_set_employee_skill_enabled,
    db_unlink_employee_skill,
    db_upsert_employee,
)

router = APIRouter()


@router.get("/api/employees")
async def list_employees():
    return JSONResponse({"employees": db_list_employees()})

@router.get("/api/employees/{emp_id}")
async def get_employee(emp_id: str):
    emp = db_get_employee(emp_id)
    if not emp:
        return JSONResponse({"error": "数字员工不存在"}, status_code=404)
    return JSONResponse(emp)

@router.get("/api/employees/{emp_id}/full")
async def get_employee_full(emp_id: str):
    emp = db_get_employee(emp_id)
    if not emp:
        return JSONResponse({"error": "数字员工不存在"}, status_code=404)
    emp_full = dict(emp)
    # 技能详情（含员工侧启停状态 enabled）
    all_skills = db_list_skills()
    skill_states = emp.get("skill_states") or {}
    emp_full["skill_details"] = []
    for s in all_skills:
        if s["id"] in emp.get("skills", []):
            sd = dict(s)
            sd["enabled"] = skill_states.get(s["id"], True)
            emp_full["skill_details"].append(sd)
    # MCP 工具详情（从 mcp_tools 表按关联的 mcp_id 取）
    all_tools = {t["id"]: t for t in db_list_mcp_tools()}
    emp_full["mcp_detail"] = [
        {"id": mid, "name": all_tools[mid]["name"], "desc": all_tools[mid]["desc"],
         "group": all_tools[mid].get("group", "")}
        for mid in emp.get("mcp_tools", []) if mid in all_tools
    ]
    # 会话记录按员工 id 映射真实业务（删除假员工后仅保留 9006 真实员工会话；已删除的持久化标记后刷新不再返回）
    mock_convs_by_id = {
        "emp-004": [
            {"id": "conv-c01", "title": "雷神设备采购比对（IDZB2607388A）", "start_time": "2026-08-05 14:10", "message_count": 4},
            {"id": "conv-c02", "title": "国药亿道教学设备比对（gyyd001）", "start_time": "2026-08-05 16:55", "message_count": 6},
            {"id": "conv-c03", "title": "药监局药品检查管理比对（IDZB2605434A）", "start_time": "2026-08-05 19:51", "message_count": 8},
        ],
        "emp-005": [
            {"id": "conv-r01", "title": "9006 合同比对结果导出优化", "start_time": "2026-08-13 10:20", "message_count": 5},
            {"id": "conv-r02", "title": "9006 经营指标看板筛选调整", "start_time": "2026-08-14 15:40", "message_count": 7},
        ],
    }
    mock_convs = mock_convs_by_id.get(emp_id, [])
    deleted_mock = set(db_get_deleted_mock_convs())
    emp_full["conversations"] = [c for c in mock_convs if c["id"] not in deleted_mock]
    return JSONResponse(emp_full)

@router.post("/api/employees")
async def create_employee(data: dict):
    import uuid as _uuid
    emp = {
        "id": f"emp-{_uuid.uuid4().hex[:6]}",
        "name": data.get("name", "新数字员工"),
        "desc": data.get("desc", ""),
        "type": data.get("type", "通用"),
        "created": datetime.now().strftime("%Y-%m-%d"),
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "skills": data.get("skills", []),
        "rag_kb": data.get("rag_kb", ""),
        "prompt": data.get("prompt", ""),
        "model": data.get("model", "deepseek-v4"),
    }
    db_upsert_employee(emp)
    return JSONResponse(emp)

@router.delete("/api/employees/{emp_id}")
async def delete_employee(emp_id: str):
    if not db_get_employee(emp_id):
        return JSONResponse({"error": "数字员工不存在"}, status_code=404)
    db_delete_employee(emp_id)
    return JSONResponse({"ok": True})

@router.patch("/api/employees/{emp_id}")
async def patch_employee(emp_id: str, data: dict):
    """更新数字员工字段。
    技能关联专用字段（不参与全量重建）：
    - skill_states: {skill_id: bool} 批量启/停用已关联技能
    - link_skills: [skill_id] 批量新增关联（默认启用）
    - unlink_skills: [skill_id] 批量解除关联
    """
    emp = db_get_employee(emp_id)
    if not emp:
        return JSONResponse({"error": "数字员工不存在"}, status_code=404)
    skill_states = data.pop("skill_states", None)
    link_skills = data.pop("link_skills", None)
    unlink_skills = data.pop("unlink_skills", None)
    if isinstance(skill_states, dict):
        for sid, st in skill_states.items():
            db_set_employee_skill_enabled(emp_id, sid, bool(st))
    if isinstance(link_skills, list):
        db_link_employee_skills(emp_id, link_skills)
    if isinstance(unlink_skills, list):
        for sid in unlink_skills:
            db_unlink_employee_skill(emp_id, sid)
    # 若执行了技能关联操作，重新读取最新状态再合并其他字段，避免重建覆盖启停
    if skill_states is not None or link_skills is not None or unlink_skills is not None:
        emp = db_get_employee(emp_id)
    for key, val in data.items():
        emp[key] = val
    emp["updated"] = datetime.now().strftime("%Y-%m-%d")
    db_upsert_employee(emp)
    return JSONResponse({"ok": True, "employee": db_get_employee(emp_id)})

