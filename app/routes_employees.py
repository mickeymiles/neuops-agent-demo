"""数字员工 CRUD 路由"""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .db import (
    db_delete_employee,
    db_get_deleted_mock_convs,
    db_get_employee,
    db_list_employees,
    db_list_mcp_tools,
    db_list_skills,
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
    # 技能详情（含 skill-mcp 关联的工具清单）
    all_skills = db_list_skills()
    emp_full["skill_details"] = [s for s in all_skills if s["id"] in emp.get("skills", [])]
    # MCP 工具详情（从 mcp_tools 表按关联的 mcp_id 取）
    all_tools = {t["id"]: t for t in db_list_mcp_tools()}
    emp_full["mcp_detail"] = [
        {"id": mid, "name": all_tools[mid]["name"], "desc": all_tools[mid]["desc"],
         "group": all_tools[mid].get("group", "")}
        for mid in emp.get("mcp_tools", []) if mid in all_tools
    ]
    # 会话记录按员工类型区分（沿用 mock 会话数据；已删除的持久化标记后刷新不再返回）
    if "经营" in emp.get("type", ""):
        mock_convs = [
            {"id": "conv-c01", "title": "雷神设备采购比对（IDZB2607388A）", "start_time": "2026-08-05 14:10", "message_count": 4},
            {"id": "conv-c02", "title": "国药亿道教学设备比对（gyyd001）", "start_time": "2026-08-05 16:55", "message_count": 6},
            {"id": "conv-c03", "title": "药监局药品检查管理比对（IDZB2605434A）", "start_time": "2026-08-05 19:51", "message_count": 8},
        ]
    else:
        mock_convs = [
            {"id": "conv-001", "title": "订单服务延迟排查", "start_time": "2026-08-08 14:30", "message_count": 12},
            {"id": "conv-002", "title": "支付服务告警分析", "start_time": "2026-08-08 11:20", "message_count": 8},
            {"id": "conv-003", "title": "数据库连接池问题", "start_time": "2026-08-07 16:45", "message_count": 15},
        ]
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
    """更新数字员工字段（skills数组等）"""
    emp = db_get_employee(emp_id)
    if not emp:
        return JSONResponse({"error": "数字员工不存在"}, status_code=404)
    for key, val in data.items():
        emp[key] = val
    emp["updated"] = datetime.now().strftime("%Y-%m-%d")
    db_upsert_employee(emp)
    return JSONResponse({"ok": True, "employee": emp})

