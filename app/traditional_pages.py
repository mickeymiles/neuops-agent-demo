"""主页面与健康检查路由

2026-08 改造：移除 /traditional /legacy 传统运维大盘假页面（已由 /ops 一体化监控平台替代）。
"""
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .config import STATIC_DIR

router = APIRouter()


@router.get("/")
async def index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/health")
async def health():
    return {"status": "ok", "service": "NeuOps Agent Demo"}
