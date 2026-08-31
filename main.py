"""
NeuOps Agent 运维对话智能工作台 Demo
FastAPI 后端 + Mock MCP 网关 + SSE 流式对话 + 统一监控探针 + 一体化运维监控平台

薄入口：组装 app、挂载路由与静态资源、初始化数据库、启动监控探针与告警引擎。
业务逻辑按领域拆分于 app/ 包，保持与原单文件版本 100% 行为兼容。
"""
import asyncio
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.alert_engine import _alert_engine_loop, seed_alert_rules
from app.config import DB_PATH, PORT, STATIC_DIR, BASE_DIR
from app.db import (
    init_bid_db, init_config_db, init_ops_db, init_session_db,
    seed_config_db, seed_mock_conversations,
    ensure_mcp_server_mapping, sync_seed_employees,
)
from app.seed_bid_kb import seed_bid_kb
from app import (
    agent_chat,
    bidding,
    routes_employees,
    routes_knowledge,
    routes_local_tools,
    routes_manage,
    routes_monitor,
    routes_ops,
    routes_procurement_agent,
    routes_tasks,
    routes_workspace,
    traditional_pages,
)
from app.probe import ProbeManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动统一监控探针与告警引擎，退出时优雅停止"""
    # 统一监控探针（服务器/容器/数据库/中间件/应用/网络）
    pm = ProbeManager()
    routes_ops.set_probe(pm)
    pm.start()
    # 业务告警检测引擎（LLM APM + ops 真实指标，后续扩展）
    threading.Thread(target=_alert_engine_loop, daemon=True).start()
    # 【恢复传统状态机】采购询比价自动调度（现轨 emp-008）：每 1 分钟拉 IMAP 邮件 + 进度/超时告警
    proc_task = asyncio.create_task(_proc_scheduler_loop())
    # 确保 emp-008 数字员工启用（传统方式）；本体轨 emp-009 暂时停用（代码保留、governor=off 零副作用）
    try:
        from app.routes_procurement_agent import mail_inquiry_register_employee
        await mail_inquiry_register_employee()
    except Exception as _e:
        print(f"[register] emp-008 enable failed: {_e}")
    # 本体轨 emp-009：默认不启动（revert 后保持零副作用）。
    # 设 ONT_SCHEDULER=1 才自走调度；与现轨并行时两套各用自己的邮箱（b3 / b4），互不影响。
    proc_ont_task = None
    if os.getenv("ONT_SCHEDULER", "0") == "1":
        try:
            from app.ontology.registration import register_emp009
            register_emp009()
            print("[register] emp-009 本体轨已启用（ONT_SCHEDULER=1）")
        except Exception as _e:
            print(f"[register] emp-009 enable failed: {_e}")
        proc_ont_task = asyncio.create_task(_ont_scheduler_loop())
    yield
    proc_task.cancel()
    if proc_ont_task:
        proc_ont_task.cancel()
    pm.stop()


async def _proc_scheduler_loop():
    """采购询比价自动调度：每 1 分钟触发 IMAP 轮询（报价+发货+备件邮件询价）+ 进度告警"""
    import httpx
    await asyncio.sleep(30)  # 启动后等 30 秒再开始
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.post("http://127.0.0.1:9007/api/procurement-agent/scheduler/tick?kind=quote", timeout=30)
                await client.post("http://127.0.0.1:9007/api/procurement-agent/scheduler/tick?kind=delivery", timeout=30)
                await client.post("http://127.0.0.1:9007/api/procurement-agent/scheduler/tick?kind=progress", timeout=30)
                # 备件邮件询价数字员工：自动解析工程师询价/供应商报价/审批人确认（1 分钟轮询，适配紧急截止）
                await client.post("http://127.0.0.1:9007/api/procurement-agent/scheduler/tick?kind=mail-inquiry", timeout=30)
        except Exception:
            pass
        await asyncio.sleep(60)  # 1 分钟


async def _ont_scheduler_loop():
    """本体轨 emp-009：全流程自走（SEEN认领+入向回复+LLM决策执行）。
    governor 放行才真正发信/落库；默认 off 时零副作用。"""
    import httpx
    await asyncio.sleep(40)
    while True:
        try:
            async with httpx.AsyncClient() as client:
                # use_llm 由 ONT_SCHEDULER_USE_LLM 控制：
                # 建议先用规则模式（0）跑通全流程，确认链路无问题后再切 1 启用 LLM 决策回路。
                _use_llm = os.getenv("ONT_SCHEDULER_USE_LLM", "0") == "1"
                await client.post("http://127.0.0.1:9007/api/ontology-emp009/run-full",
                                  json={"use_llm": _use_llm}, timeout=60)
        except Exception:
            pass
        await asyncio.sleep(60)  # 1 分钟


app = FastAPI(title="NeuOps Agent Demo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request, call_next):
    """静态资源与 API 响应禁用缓存，避免浏览器/服务器出现旧版前端"""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# 路由挂载（顺序与原 main.py 定义顺序保持一致，避免路径匹配差异）
app.include_router(agent_chat.router)
app.include_router(routes_workspace.router)
app.include_router(traditional_pages.router)
app.include_router(routes_employees.router)
app.include_router(routes_tasks.router)
app.include_router(routes_monitor.router)
app.include_router(routes_knowledge.router)
app.include_router(routes_ops.router)
app.include_router(routes_ops.page_router)
app.include_router(routes_manage.page_router)
app.include_router(bidding.router)
app.include_router(routes_procurement_agent.router)
app.include_router(routes_local_tools.router)  # 本地 11 个 MCP Tool HTTP 端点
# 本体轨 emp-009（NO-012）：独立路由，与现轨并存
from app.ontology import routes as routes_ontology
app.include_router(routes_ontology.router)

# 静态资源
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# 投标工作台上传/生成成果（demo 演示网页预览：/uploads/bid/{pid}/outputs/{id}.html）
app.mount("/uploads", StaticFiles(directory=os.path.join(BASE_DIR, "uploads"), check_dir=False), name="uploads")

# 初始化数据库与种子数据（模块加载即执行，与原 main.py 行为一致）
init_session_db()
init_config_db()
init_ops_db()
init_bid_db()
seed_bid_kb()
seed_mock_conversations()
seed_config_db()
sync_seed_employees()
ensure_mcp_server_mapping()
seed_alert_rules()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
