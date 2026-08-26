"""数字员工 CRUD 路由"""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .routes_manage import _resolve_biz_public_base

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

WORKBENCH_COMPONENT_TYPES = {"metric", "list", "action", "note", "business_app"}
WORKBENCH_COMPONENT_KEYS = {"id", "type", "title", "items", "content"}
WORKBENCH_ITEM_KEYS = {
    "metric": {"label", "value", "trend"},
    "list": {"label", "detail", "status"},
    "action": {"label", "prompt"},
}


def _default_workbench(emp: dict) -> dict:
    emp_type = emp.get("type", "通用")
    presets = {
        "运维巡检": (["健康实体", "待巡检", "高风险"], ["执行全域巡检", "查看异常实体"]),
        "告警根因": (["活跃告警", "高危告警", "待确认"], ["分析未恢复告警", "生成根因报告"]),
        "运维开发": (["错误日志", "待分析", "方案草稿"], ["分析系统错误", "生成排查脚本"]),
        "经营分析": (["签单毛利率", "回款毛利率", "高风险合同"], ["分析经营指标", "探查合同明细"]),
        "平台编辑": (["待审规则", "配置版本", "影响范围"], ["检查规则配置", "生成变更方案"]),
        "项目治理": (["风险项目", "工时异常", "四算越界"], ["检查四算约束", "生成整改清单"]),
        "售前投标": (["进行中方案", "待响应条款", "可复用模板"], ["组装技术方案", "生成点对点应答"]),
    }
    metric_labels, actions = presets.get(emp_type, (["待办事项", "运行任务", "可用技能"], ["开始业务分析", "查看工作摘要"]))
    components = [
        {
            "id": "overview",
            "type": "metric",
            "title": "业务概览",
            "items": [{"label": label, "value": "--", "trend": "待同步"} for label in metric_labels],
        },
        {
            "id": "focus",
            "type": "list",
            "title": "重点关注",
            "items": [{"label": "暂无待处理事项", "detail": "对话或业务数据将汇总到这里", "status": "正常"}],
        },
        {
            "id": "actions",
            "type": "action",
            "title": "快捷操作",
            "items": [{"label": label, "prompt": f"@{emp.get('name', '数字员工')} {label}"} for label in actions],
        },
    ]
    if emp_type == "经营分析":
        components.insert(0, {
            "id": "contract-platform",
            "type": "business_app",
            "title": "合同经营分析平台",
        })
    return {
        "title": f"{emp.get('name', '数字员工')}工作台",
        "description": f"面向{emp_type}场景的业务视图，数据接入后将按配置自动刷新。",
        "components": components,
    }


def _validate_workbench(workbench):
    if workbench is None:
        return None
    if not isinstance(workbench, dict):
        raise ValueError("workbench 必须是对象或 null")
    if set(workbench) - {"title", "description", "components"}:
        raise ValueError("workbench 包含不支持的字段")
    for key in ("title", "description"):
        if not isinstance(workbench.get(key, ""), str) or len(workbench.get(key, "")) > 120:
            raise ValueError(f"workbench.{key} 必须是长度不超过 120 的字符串")
    components = workbench.get("components")
    if not isinstance(components, list) or not 1 <= len(components) <= 12:
        raise ValueError("workbench.components 必须包含 1-12 个组件")
    component_ids = set()
    for component in components:
        if not isinstance(component, dict) or set(component) - WORKBENCH_COMPONENT_KEYS:
            raise ValueError("工作台组件结构无效")
        component_id = component.get("id")
        component_type = component.get("type")
        if not isinstance(component_id, str) or not component_id or len(component_id) > 40 or component_id in component_ids:
            raise ValueError("组件 id 必须唯一且长度不超过 40")
        component_ids.add(component_id)
        if component_type not in WORKBENCH_COMPONENT_TYPES:
            raise ValueError("组件 type 不在白名单中")
        if not isinstance(component.get("title", ""), str) or len(component.get("title", "")) > 60:
            raise ValueError("组件 title 必须是长度不超过 60 的字符串")
        if component_type == "business_app":
            if "items" in component or "content" in component:
                raise ValueError("业务系统组件不接受自定义地址或内容")
            continue
        if component_type == "note":
            if not isinstance(component.get("content", ""), str) or len(component.get("content", "")) > 1000:
                raise ValueError("说明组件 content 必须是长度不超过 1000 的字符串")
            continue
        items = component.get("items")
        if not isinstance(items, list) or len(items) > 12:
            raise ValueError("组件 items 最多包含 12 项")
        allowed_keys = WORKBENCH_ITEM_KEYS[component_type]
        for item in items:
            if not isinstance(item, dict) or set(item) - allowed_keys:
                raise ValueError("组件条目结构无效")
            if any(not isinstance(value, str) or len(value) > 300 for value in item.values()):
                raise ValueError("组件条目字段必须是长度不超过 300 的字符串")
    return workbench


@router.get("/api/workbench/config")
async def get_workbench_config(request: Request):
    return JSONResponse({"contract_base_url": _resolve_biz_public_base(request)})


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
    emp_full["workbench_custom"] = emp.get("workbench") is not None
    emp_full["workbench"] = emp.get("workbench") or _default_workbench(emp)
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
            {"id": "conv-r01", "title": "9006 价格比对规则关闭方案", "start_time": "2026-08-13 10:20", "message_count": 5},
            {"id": "conv-r02", "title": "9006 合同数据排除规则新增", "start_time": "2026-08-14 15:40", "message_count": 7},
        ],
        "emp-006": [
            {"id": "conv-p01", "title": "集团四算刚性约束监控预警", "start_time": "2026-08-15 09:10", "message_count": 6},
            {"id": "conv-p02", "title": "8月日报工时合规整改清单", "start_time": "2026-08-15 17:30", "message_count": 9},
            {"id": "conv-p03", "title": "7月集团指标双按完成率复盘", "start_time": "2026-08-16 10:05", "message_count": 5},
        ],
        "emp-007": [
            {"id": "conv-b01", "title": "某银行一体化运维平台技术方案组装", "start_time": "2026-08-15 11:20", "message_count": 8},
            {"id": "conv-b02", "title": "某政务云项目招标点对点应答", "start_time": "2026-08-16 09:40", "message_count": 7},
        ],
    }
    mock_convs = mock_convs_by_id.get(emp_id, [])
    deleted_mock = set(db_get_deleted_mock_convs())
    emp_full["conversations"] = [c for c in mock_convs if c["id"] not in deleted_mock]

    # 对于没有 mock 对话的员工，从真实会话库查询
    if not emp_full["conversations"]:
        try:
            from app.db.sessions import db_get_employee_conversations
            real_convs = db_get_employee_conversations(emp_id)
            if real_convs:
                emp_full["conversations"] = real_convs
        except Exception:
            pass  # 会话库不可用时保持空列表

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
    if "workbench" in data:
        try:
            data["workbench"] = _validate_workbench(data["workbench"])
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
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

