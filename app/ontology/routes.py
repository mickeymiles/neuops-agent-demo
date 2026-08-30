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


# ── 阶段 B 治理 / 受控执行 ──────────────────────────────────────────

@router.get("/governor")
def get_governor():
    from . import execution
    return {"success": True, "governor": execution.governor()}


@router.post("/governor")
async def set_governor(request: Request):
    body = await request.json()
    from . import execution
    try:
        g = execution.set_governor(mode=body.get("mode", "off"),
                                   roll=float(body.get("roll", 0)),
                                   exec_enabled=bool(body.get("exec_enabled", False)))
        return {"success": True, "governor": g}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/run")
async def run_managed(request: Request):
    """受控执行：在 governor 放行下，采集新工程师询价→建 O_Task→发询价B。
    use_llm=true 走 LLM 决策。默认仅能力演示，governor=off 时不产生任何变更。"""
    body = await request.json()
    use_llm = bool(body.get("use_llm", False))
    from .ingest import fetch_new_inquiry_facts
    from . import mail_gateway as mg, execution, store
    from .engine import decide_action
    from .decision import build_fact_context
    try:
        facts = fetch_new_inquiry_facts(mg, hours=int(body.get("hours", 2)), store=store)
    except Exception as e:
        return {"success": False, "error": f"inbox scan failed: {e}"}
    created, executed = [], []
    for it in facts:
        fields = it["fields"]
        ctx = dict(fields)
        aid, reason, via_llm = decide_action(ctx, use_llm=use_llm)
        # 建任务占位（O_Task）
        tid = f"OT-{shake(fields.get('message_id'))}"
        task = {"task_id": tid, "from_email": fields.get("from_email", ""),
                "threat_msg_id": fields.get("message_id", ""), "urgency_raw": fields.get("urgent", ""),
                "status": "PRE", "mode": "ontology", "spare_info": fields,
                "internal_status": "R_INIT", "external_status": "R_SEND"}
        created.append({"task_id": tid, "proposed_action": aid, "reason": reason, "via_llm": via_llm})
        if execution.needs_exec():
            ok, detail = execution.execute_action(aid, task, ctx, mg=mg, force=False)
            executed.append({"task_id": tid, "ok": ok, "detail": detail})
        elif fields.get("from_email"):
            # 未放行时也建 O_Task 占位（仅诊断，不触发真实发信）
            execution.execute_action("createTask", task, ctx, mg=mg, force=True)
    return {"success": True, "facts": len(facts), "created": created, "executed": executed,
            "governor": execution.governor()}


def shake(s: str) -> str:
    import hashlib
    return hashlib.md5((s or "x").encode()).hexdigest()[:8].upper()