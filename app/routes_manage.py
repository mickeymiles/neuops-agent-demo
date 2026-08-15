# -*- coding: utf-8 -*-
"""后台管理页面路由：/manage（能力配置与业务成果）

仅承担页面路由职责，不重复实现业务 API：
- 工作成果 / 知识库 / MCP 服务与工具 / 技能中心 / 数字员工配置
  全部复用 routes_workspace.py / routes_knowledge.py / routes_employees.py 现有接口。

页面打开时注入 9006 业务系统外链地址（避免前端硬编码）。
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from .config import BIZ_9006_BASE

page_router = APIRouter(tags=["manage-page"])

MANAGE_HTML = Path(__file__).resolve().parent.parent / "static" / "manage.html"


@page_router.get("/manage")
def manage_page():
    """/manage 后台管理页面（浏览器直接访问入口）"""
    if not MANAGE_HTML.exists():
        raise HTTPException(404, "manage.html not found")
    html = MANAGE_HTML.read_text(encoding="utf-8")
    # 注入 9006 业务平台外链地址（避免前端硬编码）
    html = html.replace("__BIZ_9006_BASE__", BIZ_9006_BASE.rstrip("/"))
    return HTMLResponse(html)
