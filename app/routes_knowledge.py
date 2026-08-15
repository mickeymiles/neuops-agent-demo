# -*- coding: utf-8 -*-
"""知识库管理 API：新建 / 上传 / 删除 / 重建索引 / 智能体绑定 / chunk 查看"""
import os
import shutil

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from . import db, knowledge

router = APIRouter()

ALLOWED_EXTS = {".txt", ".md", ".xlsx", ".pdf", ".docx"}


@router.get("/api/knowledge/bases")
async def list_bases():
    kbs = db.db_list_knowledge_bases()
    # 附带绑定员工名
    for kb in kbs:
        kb["employees"] = db.db_get_kb_employees(kb["id"])
    return JSONResponse({"success": True, "knowledge_bases": kbs})


@router.post("/api/knowledge/bases")
async def create_base(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    desc = (body.get("description") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "知识库名称不能为空"}, status_code=400)
    kb_id = db.db_create_knowledge_base(name, desc)
    return JSONResponse({"success": True, "knowledge_base": db.db_get_knowledge_base(kb_id)})


@router.post("/api/knowledge/bases/{kb_id}")
async def update_base(kb_id: str, request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "知识库名称不能为空"}, status_code=400)
    db.db_rename_knowledge_base(kb_id, name, body.get("description") or "")
    return JSONResponse({"success": True, "knowledge_base": db.db_get_knowledge_base(kb_id)})


@router.delete("/api/knowledge/bases/{kb_id}")
async def delete_base(kb_id: str):
    if not db.db_get_knowledge_base(kb_id):
        return JSONResponse({"success": False, "error": "知识库不存在"}, status_code=404)
    # 清理向量 + 上传文件
    knowledge.delete_kb_vectors(kb_id)
    upload_dir = os.path.join(knowledge.UPLOAD_DIR, kb_id)
    if os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)
    db.db_delete_knowledge_base(kb_id)
    return JSONResponse({"success": True})


@router.post("/api/knowledge/{kb_id}/upload")
async def upload_files(kb_id: str, files: list[UploadFile] = File(...)):
    """上传文件 → 保存原文件 → 解析切块 → 写入向量库"""
    if not db.db_get_knowledge_base(kb_id):
        return JSONResponse({"success": False, "error": "知识库不存在"}, status_code=404)
    target_dir = knowledge.get_upload_dir(kb_id)
    saved = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_EXTS:
            continue
        # 防路径穿越
        safe_name = os.path.basename(f.filename or "file" + ext)
        dst = os.path.join(target_dir, safe_name)
        with open(dst, "wb") as out:
            content = f.file.read()
            out.write(content)
        saved.append(dst)

    if not saved:
        return JSONResponse({"success": False, "error": "没有可识别的文件（支持 txt/md/xlsx/pdf/docx）"}, status_code=400)

    result = knowledge.build_kb_index(kb_id, saved)
    return JSONResponse({"success": True, "result": result})


@router.get("/api/knowledge/{kb_id}/chunks")
async def list_chunks(kb_id: str, offset: int = 0, limit: int = 50):
    total = db.db_count_kb_chunks(kb_id)
    chunks = db.db_list_kb_chunks(kb_id, offset=offset, limit=limit)
    return JSONResponse({"success": True, "total": total, "chunks": chunks})


@router.delete("/api/knowledge/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str):
    # 先查该 chunk 归属
    info = db.db_get_kb_chunk(chunk_id)
    if not info:
        return JSONResponse({"success": False, "error": "chunk 不存在"}, status_code=404)
    db.db_delete_kb_chunk(chunk_id)
    knowledge.delete_chunk_vector(info["kb_id"], info["chunk_index"], info["doc_name"])
    knowledge.rebuild_stats(info["kb_id"])
    return JSONResponse({"success": True})


@router.post("/api/knowledge/{kb_id}/rebuild")
async def rebuild_index(kb_id: str):
    """从 uploads/{kb_id}/ 目录重新构建索引"""
    if not db.db_get_knowledge_base(kb_id):
        return JSONResponse({"success": False, "error": "知识库不存在"}, status_code=404)
    target_dir = os.path.join(knowledge.UPLOAD_DIR, kb_id)
    files = []
    if os.path.isdir(target_dir):
        for n in os.listdir(target_dir):
            if os.path.splitext(n)[1].lower() in ALLOWED_EXTS:
                files.append(os.path.join(target_dir, n))
    if not files:
        return JSONResponse({"success": False, "error": "目录中没有可重建的文件"}, status_code=400)
    result = knowledge.build_kb_index(kb_id, files)
    return JSONResponse({"success": True, "result": result})


@router.post("/api/knowledge/{kb_id}/bind")
async def bind_employee(kb_id: str, request: Request):
    """覆盖式设置绑定：body: {employee_ids: [..]} 为最终绑定的员工集合"""
    if not db.db_get_knowledge_base(kb_id):
        return JSONResponse({"success": False, "error": "知识库不存在"}, status_code=404)
    body = await request.json()
    target = set(body.get("employee_ids") or [])
    # 先解除当前所有绑定
    for emp in db.db_get_kb_employees(kb_id):
        emp_id = emp["id"]
        ids = db.db_get_employee_kb_ids(emp_id)
        ids = [i for i in ids if i != kb_id]
        db.db_bind_employee_kb(emp_id, ids)
    # 再绑定目标员工
    for emp_id in target:
        ids = db.db_get_employee_kb_ids(emp_id)
        if kb_id not in ids:
            db.db_bind_employee_kb(emp_id, ids + [kb_id])
    return JSONResponse({"success": True})
