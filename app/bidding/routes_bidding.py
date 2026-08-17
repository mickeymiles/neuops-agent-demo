# -*- coding: utf-8 -*-
"""投标工作台 API：项目 CRUD / 上传 / 拆标 / 生成 / 自检 / 导出"""
import os
import re

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .. import db, knowledge
from .bid_engine import (
    BID_UPLOAD_ROOT,
    check_compliance,
    export_document,
    generate_document,
    parse_bid_document,
)

router = APIRouter()

ALLOWED_EXTS = {".docx", ".pdf", ".xlsx", ".txt", ".md"}


def _project_dir(pid: int) -> str:
    d = os.path.join(BID_UPLOAD_ROOT, str(pid))
    os.makedirs(d, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    """去除路径穿越字符"""
    return re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", name or "").strip("_")


# ---------------- 项目 CRUD ----------------

@router.get("/api/bid/projects")
async def list_projects():
    return JSONResponse({"success": True, "projects": db.bid_list_projects()})


@router.post("/api/bid/projects")
async def create_project(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "项目名称不能为空"}, status_code=400)
    proj = db.bid_create_project(
        name=name,
        tenderee=(body.get("tenderee") or "").strip(),
        industry=(body.get("industry") or "").strip(),
        budget=float(body.get("budget") or 0),
        deadline=(body.get("deadline") or "").strip(),
    )
    return JSONResponse({"success": True, "project": proj})


@router.get("/api/bid/projects/{pid}")
async def get_project(pid: int):
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    proj["files"] = _list_files(pid)
    return JSONResponse({"success": True, "project": proj})


@router.patch("/api/bid/projects/{pid}")
async def update_project(pid: int, request: Request):
    body = await request.json()
    proj = db.bid_update_project(pid, **body)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    return JSONResponse({"success": True, "project": proj})


@router.delete("/api/bid/projects/{pid}")
async def delete_project(pid: int):
    ok = db.bid_delete_project(pid)
    if not ok:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    # 清理磁盘目录
    import shutil
    shutil.rmtree(os.path.join(BID_UPLOAD_ROOT, str(pid)), ignore_errors=True)
    return JSONResponse({"success": True})


# ---------------- 上传 / 文件 ----------------

def _list_files(pid: int):
    """项目规范书文件列表（原文件 + 抽取文本）"""
    d = _project_dir(pid)
    files = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            full = os.path.join(d, fn)
            if os.path.isfile(full) and fn not in ("outputs", "extracted"):
                files.append({"name": fn, "size": os.path.getsize(full)})
    return files


@router.post("/api/bid/projects/{pid}/upload")
async def upload_files(pid: int, files: list[UploadFile] = File(...)):
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    saved, failed = [], []
    d = _project_dir(pid)
    ext_dir = os.path.join(d, "extracted")
    os.makedirs(ext_dir, exist_ok=True)
    for f in files:
        raw_name = f.filename or ""
        ext = os.path.splitext(raw_name)[1].lower()
        if ext not in ALLOWED_EXTS:
            failed.append({"name": raw_name, "error": f"不支持的格式 {ext}"})
            continue
        safe = _safe_name(raw_name)
        if not safe:
            safe = f"file_{int(__import__('time').time())}{ext}"
        target = os.path.join(d, safe)
        counter = 1
        while os.path.exists(target):
            base, e = os.path.splitext(safe)
            target = os.path.join(d, f"{base}_{counter}{e}")
            counter += 1
        with open(target, "wb") as out:
            out.write(f.file.read())
        # 抽取文本供拆标使用
        text = knowledge.parse_document(target)
        if text:
            txt_name = os.path.splitext(os.path.basename(target))[0] + ".txt"
            with open(os.path.join(ext_dir, txt_name), "w", encoding="utf-8") as tf:
                tf.write(text)
        saved.append(os.path.basename(target))
    if saved:
        db.bid_set_status(pid, "已上传")
    return JSONResponse({"success": bool(saved), "saved": saved, "failed": failed,
                         "files": _list_files(pid)})


# ---------------- 拆标 / 生成 / 自检 / 导出 ----------------

@router.post("/api/bid/projects/{pid}/parse")
async def do_parse(pid: int):
    try:
        report = parse_bid_document(pid)
        return JSONResponse({"success": True, "report": report})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"拆标失败: {e}"}, status_code=500)


@router.post("/api/bid/projects/{pid}/generate")
async def do_generate(pid: int, request: Request):
    body = await request.json()
    doc_type = body.get("type") or "tech_proposal"
    try:
        doc = generate_document(pid, doc_type)
        return JSONResponse({"success": True, "doc": doc})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"生成失败: {e}"}, status_code=500)


@router.post("/api/bid/projects/{pid}/check")
async def do_check(pid: int):
    try:
        result = check_compliance(pid)
        return JSONResponse({"success": True, "result": result})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"自检失败: {e}"}, status_code=500)


@router.get("/api/bid/projects/{pid}/export/{doc_id}")
async def do_export(pid: int, doc_id: str, fmt: str = "md"):
    try:
        path = export_document(pid, doc_id, fmt)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" \
            if fmt == "docx" else "text/markdown; charset=utf-8"
        fname = f"{doc_id}.{fmt}"
        return FileResponse(path, media_type=media, filename=fname)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"导出失败: {e}"}, status_code=500)
