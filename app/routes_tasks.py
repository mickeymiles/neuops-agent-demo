async def fetch_etl_jobs():
    """从 9006 拉取定时 ETL 任务，转为长期任务格式（轨道A 关联）"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ETL_9006_BASE}/api/etl/jobs")
            data = r.json()
        jobs = data.get('jobs', [])
        result = []
        for j in jobs:
            result.append({
                'id': 'etl-' + j['job_key'],
                'name': j['job_name'],
                'status': 'running' if j.get('status') == 'running' else 'stopped',
                'description': j.get('description', ''),
                'calculation_logic': j.get('calculation_logic', ''),
                'schedule': j.get('schedule', ''),
                'update_time': j.get('last_run') or '未执行',
                'source': '9006',
                'executions': ([{'time': j['last_run'], 'status': 'success', 'thread_id': j['job_key']}]
                               if j.get('last_run') else []),
            })
        return result
    except Exception:
        return []


"""长期任务 CRUD 路由（对接 9006 ETL 服务）"""

from datetime import datetime

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .config import ETL_9006_BASE
from .db import (
    db_create_long_task,
    db_delete_long_task,
    db_get_long_task,
    db_list_long_tasks,
    db_update_long_task,
)

router = APIRouter()


@router.get("/api/long-tasks")
async def list_long_tasks():
    etl_tasks = await fetch_etl_jobs()
    return JSONResponse({"tasks": db_list_long_tasks() + etl_tasks})

@router.get("/api/long-tasks/{task_id}")
async def get_long_task(task_id: str):
    task = db_get_long_task(task_id)
    if not task:
        return JSONResponse({"error": "长期任务不存在"}, status_code=404)
    return JSONResponse(task)

@router.get("/api/long-tasks/{task_id}/executions")
async def get_task_executions(task_id: str):
    task = db_get_long_task(task_id)
    if not task:
        return JSONResponse({"error": "长期任务不存在"}, status_code=404)
    return JSONResponse({"executions": task.get("executions", [])})

@router.post("/api/long-tasks")
async def create_long_task(data: dict):
    import uuid as _uuid
    task = {
        "id": f"lt-{_uuid.uuid4().hex[:6]}",
        "name": data.get("name", "新长期任务"),
        "status": "running",
        "description": data.get("description", ""),
        "employee_id": data.get("employee_id", ""),
        "schedule": data.get("schedule", "手动触发"),
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "executions": [],
    }
    db_create_long_task(task)
    return JSONResponse(task)

@router.patch("/api/long-tasks/{task_id}")
async def update_long_task(task_id: str, data: dict):
    task = db_get_long_task(task_id)
    if not task:
        return JSONResponse({"error": "长期任务不存在"}, status_code=404)
    for k, v in data.items():
        task[k] = v
    task["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db_update_long_task(task_id, task)
    return JSONResponse(task)

@router.delete("/api/long-tasks/{task_id}")
async def delete_long_task(task_id: str):
    if not db_get_long_task(task_id):
        return JSONResponse({"error": "长期任务不存在"}, status_code=404)
    db_delete_long_task(task_id)
    return JSONResponse({"ok": True})


@router.post("/api/long-tasks/{task_id}/run")
async def run_long_task(task_id: str):
    """触发 9006 定时 ETL 任务（轨道A 关联）"""
    if not task_id.startswith('etl-'):
        return JSONResponse({'success': False, 'error': '该任务不支持手动触发'}, status_code=400)
    job_key = task_id[4:]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{ETL_9006_BASE}/api/etl/run/{job_key}")
        return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({'success': False, 'error': f'9006 连接失败: {e}'})


@router.post("/api/long-tasks/{task_id}/start")
async def start_long_task(task_id: str):
    """启动 9006 ETL 任务（进入自动调度）"""
    if not task_id.startswith('etl-'):
        return JSONResponse({'success': False, 'error': '该任务不支持启动'}, status_code=400)
    job_key = task_id[4:]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{ETL_9006_BASE}/api/etl/jobs/{job_key}/start")
        return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({'success': False, 'error': f'9006 连接失败: {e}'})


@router.post("/api/long-tasks/{task_id}/stop")
async def stop_long_task(task_id: str):
    """停止 9006 ETL 任务（退出自动调度）"""
    if not task_id.startswith('etl-'):
        return JSONResponse({'success': False, 'error': '该任务不支持停止'}, status_code=400)
    job_key = task_id[4:]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{ETL_9006_BASE}/api/etl/jobs/{job_key}/stop")
        return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({'success': False, 'error': f'9006 连接失败: {e}'})


@router.get("/api/long-tasks/{task_id}/detail")
async def detail_long_task(task_id: str):
    """获取 9006 ETL 任务详情（含计算逻辑 + 执行记录）"""
    if not task_id.startswith('etl-'):
        return JSONResponse({'error': '该任务无详情'}, status_code=404)
    job_key = task_id[4:]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{ETL_9006_BASE}/api/etl/jobs/{job_key}")
        return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({'error': f'9006 连接失败: {e}'}, status_code=500)

