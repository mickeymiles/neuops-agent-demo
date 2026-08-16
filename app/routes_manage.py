# -*- coding: utf-8 -*-
"""后台管理页面路由：/manage（能力配置与业务成果）

仅承担页面路由职责，不重复实现业务 API：
- 工作成果 / 知识库 / MCP 服务与工具 / 技能中心 / 数字员工配置
  全部复用 routes_workspace.py / routes_knowledge.py / routes_employees.py 现有接口。

页面打开时注入 9006 业务系统外链地址（避免前端硬编码）。
"""
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .config import BIZ_9006_BASE, BIZ_9006_PUBLIC_BASE

page_router = APIRouter(tags=["manage-page"])

MANAGE_HTML = Path(__file__).resolve().parent.parent / "static" / "manage.html"


def _resolve_biz_public_base(request: Request) -> str:
    """解析注入前端的工作成果外链地址。

    优先级：
    1. 环境变量显式配置 BIZ_9006_PUBLIC_BASE（部署方指定的服务器公网地址）；
    2. 环境变量 BIZ_9006_BASE 显式配置为非本机地址（127.0.0.1/localhost 之外）；
    3. 按浏览器访问后台的主机名推导 http(s)://<hostname>:9006，
       保证用户通过服务器 IP/域名访问时，跳转的是同一台服务器上的 9006，
       而不是访问者本机的 127.0.0.1。
    """
    if BIZ_9006_PUBLIC_BASE:
        return BIZ_9006_PUBLIC_BASE.rstrip("/")
    parsed = urlparse(BIZ_9006_BASE)
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        return BIZ_9006_BASE.rstrip("/")
    host = request.headers.get("host") or ""
    hostname = host.split(":")[0]
    if not hostname:
        return BIZ_9006_BASE.rstrip("/")
    scheme = "https" if request.url.scheme == "https" else "http"
    port = parsed.port or 9006
    return f"{scheme}://{hostname}:{port}"


@page_router.get("/manage")
def manage_page(request: Request):
    """/manage 后台管理页面（浏览器直接访问入口）"""
    if not MANAGE_HTML.exists():
        raise HTTPException(404, "manage.html not found")
    html = MANAGE_HTML.read_text(encoding="utf-8")
    # 注入 9006 业务平台外链地址（跟随访问主机指向服务器，避免跳转到本机 127.0.0.1）
    html = html.replace("__BIZ_9006_BASE__", _resolve_biz_public_base(request))
    return HTMLResponse(html)
