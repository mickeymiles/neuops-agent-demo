#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""49 服务器真实向量知识库 MCP 服务（独立 FastAPI，不依赖 app 包）。
协议与 122 mcp_gateway 兼容：POST/GET {base}/tools/{name}，参数走 query-string。
返回格式与 tool_response 一致：{tool, success, timestamp, data_source, data}。
"""
import os
import threading
from datetime import datetime
from typing import List, Optional

import chromadb
from fastapi import FastAPI, Query
from pydantic import BaseModel

CHROMA_DIR = os.environ.get("KB_CHROMA_DIR", "/home/ubuntu/neuops-kb-mcp/chroma_data")
COLLECTION = os.environ.get("KB_COLLECTION", "bid_knowledge")
MODEL = os.environ.get("KB_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
TOP_K = 8

app = FastAPI(title="NeuOps 真实向量知识库 MCP(49)", version="1.0.0")

_client = None
_collection = None
_embed_model = None
_lock = threading.Lock()


def _get_backend():
    global _client, _collection, _embed_model
    with _lock:
        if _collection is not None:
            return _collection, _embed_model
        from fastembed import TextEmbedding
        _embed_model = TextEmbedding(model_name=MODEL)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        return _collection, _embed_model


def tool_response(tool: str, success: bool, data: dict, **extra) -> dict:
    ds = extra.pop("source", "chroma-49")
    return {
        "tool": tool,
        "success": success,
        "timestamp": datetime.now().isoformat(),
        "data_source": ds,
        "data": data,
        **extra,
    }


@app.get("/health")
def health():
    try:
        coll, _ = _get_backend()
        return {
            "status": "ok",
            "source": "kb-mcp-49",
            "collection": COLLECTION,
            "count": coll.count(),
        }
    except Exception as e:
        return {"status": "error", "source": "kb-mcp-49", "error": str(e)}


@app.get("/tools/knowledge_bases")
@app.post("/tools/knowledge_bases")
def knowledge_bases():
    try:
        coll, _ = _get_backend()
        metas = coll.get(include=["metadatas"])["metadatas"] or []
        industries = {}
        for m in metas:
            ind = (m or {}).get("industry", "未知")
            industries.setdefault(ind, 0)
            industries[ind] += 1
        return tool_response("knowledge_bases", True, {
            "collection": COLLECTION,
            "count": coll.count(),
            "industries": industries,
        })
    except Exception as e:
        return tool_response("knowledge_bases", False, {"error": str(e)})


@app.get("/tools/kb_knowledge_read")
@app.post("/tools/kb_knowledge_read")
def kb_knowledge_read(
    keyword: str = Query(default=""),
    limit: int = Query(default=5),
    industry: str = Query(default=""),
):
    """真实向量检索内部知识库、历史方案、中标库（49 Chroma + bge-small-zh）"""
    if not keyword:
        return tool_response("kb_knowledge_read", False,
                             {"error": "请提供 keyword 检索关键词"})
    try:
        coll, _ = _get_backend()
        n = min(max(limit, 1), TOP_K)
        if industry:
            where = {"industry": industry}
            hits = coll.query(query_texts=[keyword], n_results=n, where=where)
        else:
            hits = coll.query(query_texts=[keyword], n_results=n)
        ids = hits.get("ids", [[]])[0]
        docs = hits.get("documents", [[]])[0]
        metas = hits.get("metadatas", [[]])[0]
        dists = hits.get("distances", [[]])[0]
        out = []
        for i in range(len(ids)):
            m = metas[i] or {}
            out.append({
                "id": ids[i],
                "industry": m.get("industry", ""),
                "scenario": m.get("scenario", ""),
                "title": m.get("title", ""),
                "summary": m.get("summary", ""),
                "amount": m.get("amount", 0),
                "win": bool(m.get("win", False)),
                "keywords": (m.get("keywords") or "").split(",") if m.get("keywords") else [],
                "content": docs[i] if docs[i] else "",
                "score": round(1 - float(dists[i]), 4) if dists[i] is not None else 0.0,
            })
        return tool_response("kb_knowledge_read", True,
                             {"keyword": keyword, "hits": out, "hit_count": len(out)},
                             source="chroma-49")
    except Exception as e:
        return tool_response("kb_knowledge_read", False, {"error": f"检索失败: {e}"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9012)
