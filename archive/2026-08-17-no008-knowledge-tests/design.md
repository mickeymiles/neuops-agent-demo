# 设计：NO-008 知识库与 RAG 测试

## 被测对象（`app/knowledge.py`）

- `parse_document(path)`：按扩展名解析 txt/md（读文本）/ xlsx（`## 工作表: {title}` + `列名: 值；列名: 值` 行），不支持返回 ""
- `chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)`：
  按空行聚合短段落 → 超长块二次切分（`chunk_size` 定长 + `overlap` 重叠）→ 丢弃 <8 字符碎片
- `_tokenize_zh(text)`：标点切分；词长 ≤4 → 整体 +2；长词按 4/3/2 字滑动窗口加权
- `_keyword_search(query, kb_ids, top_k)`：`_tokenize_zh` 取 top20 词，对
  `db.db_list_kb_chunks(kb_id, limit=800)` 逐条打分（命中词频累计），
  排序键 `(-hit_count, -score)`，`score = round(min(0.99, 0.4 + score/60), 4)`
- `search_knowledge(query, kb_ids=None, top_k=5)`：空输入 → []；向量不可用（无 chroma/embedder）→ 降级 `_keyword_search`

## 测试策略

- 纯函数直接测（parse/chunk/tokenize），文件用 tmp_path
- `_keyword_search` / `search_knowledge` 用唯一 `kb-test-{uuid}` 前缀写真实 db
  （`db_add_kb_chunks`），`finally` 中 `db_clear_kb_chunks` 清理
- xlsx 解析用 openpyxl 构造临时工作簿

## 关键断言

- chunk 相邻块重叠：`chunks[i+1].startswith(chunks[i][-overlap:])`
- 碎片过滤：全部长度 < 8 的文本 → 空列表
- 关键词降级：query 命中 chunk 内容 → 返回该 doc 且 score ∈ (0, 1)
