#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""49 真实向量知识库构建脚本：
1) 用 fastembed BAAI/bge-small-zh-v1.5 真实生成 embedding
2) 写入 Chroma PersistentClient（/home/ubuntu/neuops-kb-mcp/chroma_data，collection=bid_knowledge）
用法: .venv/bin/python3 build_kb.py [--rebuild]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kb_seed_data import ALL_DOCS, doc_to_text

CHROMA_DIR = os.environ.get("KB_CHROMA_DIR", "/home/ubuntu/neuops-kb-mcp/chroma_data")
COLLECTION = os.environ.get("KB_COLLECTION", "bid_knowledge")
MODEL = os.environ.get("KB_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="重建 collection")
    args = parser.parse_args()

    print(f"[1/4] 加载 embedding 模型: {MODEL} ...")
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=MODEL)
    print("     模型加载完成")

    print(f"[2/4] 打开 Chroma: {CHROMA_DIR}")
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    if args.rebuild:
        try:
            client.delete_collection(COLLECTION)
            print(f"     已删除旧 collection {COLLECTION}")
        except Exception:
            pass
    coll = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    existing = coll.count()
    print(f"     当前 collection 文档数: {existing}")

    docs = [doc_to_text(d) for d in ALL_DOCS]
    ids = [d["id"] for d in ALL_DOCS]
    metas = [{
        "industry": d["industry"],
        "scenario": d["scenario"],
        "title": d["title"],
        "summary": d["summary"],
        "amount": int(d["amount"]),
        "win": int(1 if d["win"] else 0),
        "keywords": ",".join(d["keywords"]),
    } for d in ALL_DOCS]

    print(f"[3/4] 真实向量化 {len(docs)} 条文档 ...")
    embeddings = list(model.embed(docs))
    emb_list = [e.tolist() for e in embeddings]

    if args.rebuild and existing == 0:
        coll.add(ids=ids, documents=docs, metadatas=metas, embeddings=emb_list)
    elif existing == 0:
        coll.add(ids=ids, documents=docs, metadatas=metas, embeddings=emb_list)
    else:
        # 增量：跳过已存在 id
        existing_ids = set(coll.get(ids=ids)["ids"])
        add_i = [i for i, _id in enumerate(ids) if _id not in existing_ids]
        if add_i:
            coll.add(
                ids=[ids[i] for i in add_i],
                documents=[docs[i] for i in add_i],
                metadatas=[metas[i] for i in add_i],
                embeddings=[emb_list[i] for i in add_i],
            )
        print(f"     增量新增 {len(add_i)} 条，跳过已有 {len(existing_ids)} 条")

    final = coll.count()
    print(f"[4/4] 完成！collection={COLLECTION} 文档总数={final}")


if __name__ == "__main__":
    main()
