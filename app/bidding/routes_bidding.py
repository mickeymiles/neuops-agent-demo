# -*- coding: utf-8 -*-
"""投标工作台 API：项目 CRUD / 上传 / 拆标 / 生成 / 自检 / 导出"""
import json
import os
import re

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .. import db, knowledge
from .bid_engine import (
    BID_FILE_CATEGORIES,
    BID_UPLOAD_ROOT,
    assemble_document,
    auto_category,
    check_compliance,
    delete_bid_template,
    export_document,
    generate_chapter,
    generate_document,
    generate_mockup,
    generate_outline,
    get_pipeline_status,
    kb_write_upload_texts,
    load_bid_template,
    parse_bid_document,
    requirements_analysis,
    run_bid_pipeline,
    save_bid_template,
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
    proj["template"] = load_bid_template(pid)
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

def _file_category(pid: int, raw_name: str) -> str:
    """从 extracted/<category>/<stem>.txt 反查分类；缺失按文件名自动识别"""
    stem = os.path.splitext(raw_name)[0]
    ext_dir = os.path.join(BID_UPLOAD_ROOT, str(pid), "extracted")
    if os.path.isdir(ext_dir):
        for cat in BID_FILE_CATEGORIES:
            if os.path.isfile(os.path.join(ext_dir, cat, f"{stem}.txt")):
                return cat
    return auto_category(raw_name)


def _list_files(pid: int):
    """项目规范书文件列表（原文件 + 抽取文本），带分类标签（FR-10）"""
    d = _project_dir(pid)
    files = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            full = os.path.join(d, fn)
            if os.path.isfile(full) and fn not in ("outputs", "extracted"):
                files.append({"name": fn, "size": os.path.getsize(full),
                              "category": _file_category(pid, fn)})
    return files


@router.post("/api/bid/projects/{pid}/upload")
async def upload_files(pid: int, files: list[UploadFile] = File(...),
                       categories: str = Form("")):
    """多文件上传。categories 为可选 JSON：「文件名 → 分类」；未指定按自动识别（FR-10）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    cat_map = {}
    if categories:
        try:
            cat_map = json.loads(categories)
        except Exception:
            cat_map = {}
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
        # 抽取文本供拆标使用，按分类独立落盘（FR-10）
        text = knowledge.parse_document(target)
        cat = cat_map.get(raw_name) or auto_category(raw_name, text or "")
        if cat not in BID_FILE_CATEGORIES:
            cat = "other"
        if text:
            cat_dir = os.path.join(ext_dir, cat)
            os.makedirs(cat_dir, exist_ok=True)
            txt_name = os.path.splitext(os.path.basename(target))[0] + ".txt"
            with open(os.path.join(cat_dir, txt_name), "w", encoding="utf-8") as tf:
                tf.write(text)
        saved.append({"name": os.path.basename(target), "category": cat})
    if saved:
        db.bid_set_status(pid, "已上传")
        # 上传即入库：抽取文本写入项目级知识库（FR-16），原文件已保留在 uploads/bid/{pid}/
        try:
            kb_write_upload_texts(pid)
        except Exception as e:
            return JSONResponse({"success": True, "saved": saved, "failed": failed,
                                 "files": _list_files(pid),
                                 "warn": f"知识库写入失败: {e}"})
    return JSONResponse({"success": bool(saved), "saved": saved, "failed": failed,
                         "files": _list_files(pid)})


# ---------------- 投标模板（FR-13） ----------------

@router.post("/api/bid/projects/{pid}/template")
async def upload_template(pid: int, file: UploadFile = File(...)):
    """上传投标模板 docx（单模板覆盖），返回模板元信息与章节树（FR-13）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    try:
        tpl = save_bid_template(pid, file.file.read(), file.filename or "")
        # 模板章节结构同步写入项目知识库（FR-16）
        try:
            kb_write_upload_texts(pid)
        except Exception:
            pass
        return JSONResponse({"success": True, "template": tpl})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"模板上传失败: {e}"}, status_code=500)


@router.delete("/api/bid/projects/{pid}/template")
async def delete_template(pid: int):
    """删除投标模板（FR-13）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    deleted = delete_bid_template(pid)
    return JSONResponse({"success": True, "deleted": deleted})


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


@router.post("/api/bid/projects/{pid}/requirements")
async def do_requirements(pid: int):
    """步骤3 需求分析：LLM 整理结构化 PRD（FR-17）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    if proj.get("status") not in ("已拆标", "已生成", "已自检", "已导出") and not (proj.get("parse_report") or {}):
        return JSONResponse({"success": False, "error": "请先完成拆标（步骤2）"}, status_code=400)
    try:
        prd = requirements_analysis(pid)
        return JSONResponse({"success": True, "prd": prd})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"需求分析失败: {e}"}, status_code=500)


@router.post("/api/bid/projects/{pid}/mockup")
async def do_mockup(pid: int):
    """步骤4 假页面生成：LLM 产出演示 HTML（FR-18）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    try:
        result = generate_mockup(pid)
        return JSONResponse({"success": True, "doc": result["doc"]})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"假页面生成失败: {e}"}, status_code=500)


@router.post("/api/bid/projects/{pid}/outline")
async def do_outline(pid: int):
    """步骤5a 章节大纲生成（FR-19）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    try:
        outline = generate_outline(pid)
        return JSONResponse({"success": True, "outline": outline})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"大纲生成失败: {e}"}, status_code=500)


@router.post("/api/bid/projects/{pid}/chapter")
async def do_chapter(pid: int, request: Request):
    """步骤5b 逐章生成/重生成（FR-19/FR-20）。body: {index, force?}"""
    body = await request.json()
    index = int(body.get("index") or 0)
    force = bool(body.get("force") or False)
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    try:
        result = generate_chapter(pid, index, force=force)
        return JSONResponse({"success": True, "chapter": result["chapter"],
                             "done": result.get("done", False)})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"章节生成失败: {e}"}, status_code=500)


@router.post("/api/bid/projects/{pid}/chapters/confirm")
async def do_confirm_chapter(pid: int, request: Request):
    """步骤5c 确认本章定稿（FR-20）。body: {index, content?} 可选覆盖草稿"""
    body = await request.json()
    index = int(body.get("index") or 0)
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    chapters = proj.get("chapters_json") or []
    if index < 1 or index > len(chapters):
        return JSONResponse({"success": False, "error": "章节序号无效"}, status_code=400)
    ch = chapters[index - 1]
    if not (ch.get("content") or "").strip():
        return JSONResponse({"success": False, "error": "本章尚无草稿，请先生成"}, status_code=400)
    if body.get("content") is not None:
        ch["content"] = str(body["content"])
    ch["confirmed"] = True
    db.bid_save_chapters(pid, chapters)
    return JSONResponse({"success": True, "chapters": chapters})


@router.post("/api/bid/projects/{pid}/assemble")
async def do_assemble(pid: int):
    """步骤6 组装导出：合并已确认章节 → 最终文档（FR-21）"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    try:
        doc = assemble_document(pid)
        return JSONResponse({"success": True, "doc": doc})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"组装失败: {e}"}, status_code=500)


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
        if fmt == "docx":
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif fmt == "html":
            media = "text/html; charset=utf-8"
        else:
            media = "text/markdown; charset=utf-8"
        fname = f"{doc_id}.{fmt}"
        return FileResponse(path, media_type=media, filename=fname)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"导出失败: {e}"}, status_code=500)


# ---------------- 一键智能起草流水线（NO-009 FR-22） ----------------

@router.post("/api/bid/projects/{pid}/pipeline/run")
async def run_pipeline(pid: int, request: Request):
    """一键智能起草：拆标→需求→演示→大纲→逐章→截图（默认停人工复核）。
    body: {auto_confirm?: bool} true 时自动确认全部章节并组装+自检+导出 docx"""
    proj = db.bid_get_project(pid)
    if not proj:
        return JSONResponse({"success": False, "error": "项目不存在"}, status_code=404)
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    auto_confirm = bool(body.get("auto_confirm"))
    try:
        result = run_bid_pipeline(pid, auto_confirm=auto_confirm)
        return JSONResponse({"success": True, **result})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"一键起草失败: {e}"}, status_code=500)


@router.get("/api/bid/projects/{pid}/pipeline/status")
async def pipeline_status(pid: int):
    """读取一键起草进度（前端步骤条轮询，FR-22/FR-23）"""
    return JSONResponse({"success": True, "status": get_pipeline_status(pid)})
