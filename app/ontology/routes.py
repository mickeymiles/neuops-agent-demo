# -*- coding: utf-8 -*-
"""本体轨（NO-012 emp-009）HTTP 路由：健康/对齐 tick/查询/emp-009 展示。
独立 FastAPI router；挂载到 main.py，与现轨 /api/procurement-agent/* 并存。
"""
from fastapi import APIRouter, Request

from . import store, actions as act, engine, schema
from .decision import build_fact_context, propose_action

router = APIRouter(prefix="/api/ontology-emp009", tags=["ontology-emp009"])


@router.get("/health")
def health():
    return {"service": "emp-009", "rotor": "ontology", "status": "ok",
            "tables": ["o_session", "o_task", "o_person", "o_email",
                       "o_supplier_quote", "o_audit_log", "o_alignment"]}


@router.get("/actions")
def list_actions():
    return {"total": len(act.list_action_ids()), "actions": act.ACTION_REGISTRY}


@router.get("/rules")
def list_rules():
    return {"total": len(knowledge_rules()), "rules": knowledge_rules()}


def knowledge_rules():
    from . import knowledge
    return knowledge.RULES


@router.get("/propose/{task_id}")
def propose(task_id: str):
    """对一个现轨任务做本体轨只读提议（不执行）。"""
    from app.db.spare_mail import spare_mail_get_task
    task = spare_mail_get_task(task_id)
    if not task:
        return {"success": False, "error": "task not found"}
    ctx = build_fact_context(task)
    action_id, next_ext, next_int, reason = propose_action(ctx)
    return {"success": True, "task_id": task_id, "proposed_action": action_id,
            "next_external": next_ext, "next_internal": next_int, "reason": reason}


@router.post("/scheduler/tick")
async def tick(request: Request):
    """Stage A：只读对照——对现轨活动任务做本体轨决策对比，不执行副作用。"""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    dry_run = bool(body.get("dry_run", True))
    from app.db.spare_mail import spare_mail_list_tasks
    tasks = spare_mail_list_tasks(page_size=500)
    active = [t for t in tasks if (t.get("status") or "") not in ("REJECTED",)]
    summary = engine.run_alignment(active, dry_run=dry_run)
    return {"success": True, "mode": "stage-A-read-only", "summary": summary}


@router.get("/alignment")
def alignment(limit: int = 100):
    return {"success": True, "records": store.list_alignment(limit=limit)}


@router.get("/audit")
def audit(biz_type: str = "", biz_id: str = "", limit: int = 100):
    return {"success": True, "records": store.list_audit(biz_type=biz_type or None,
                                                          biz_id=biz_id or None, limit=limit)}


@router.get("/tasks")
def list_tasks():
    return {"success": True, "tasks": store.list_tasks()}