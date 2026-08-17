# 变更提案：NO-008 知识库与 RAG 补充测试覆盖

- 编号：`20260817-no008-knowledge-tests`
- 日期：2026-08-17
- 类型：测试补齐（规格回填闭环）
- 涉及规格：NO-008 知识库与 RAG

## 为什么（Why）

NO-008 知识库与 RAG（文档解析 / 切块 / 分词 / 关键词降级检索）为存量核心功能，
但 `specs/TRACEABILITY.md` 标注其**无测试覆盖**。需补齐单元测试满足
"测试绑定规格（# NO-008 FR-x）"。

## 范围（In / Out of Scope）

- In scope：新增 `tests/test_knowledge.py`，覆盖 NO-008 的：
  - `parse_document`：txt / md / xlsx 解析、不支持扩展名返回空
  - `chunk_text`：空文本、短段落聚合、定长切块 + 重叠、过短碎片过滤
  - `_tokenize_zh`：短词/长词窗口分词频率
  - `_keyword_search`：关键词匹配打分排序（真实 db 隔离数据，测后清理）
  - `search_knowledge`：空输入降级、向量不可用时回退关键词检索
- Out of scope：不触碰真实向量库 / Embedding 服务（chroma 可用时相关分支跳过）；
  不改动 `app/knowledge.py` 逻辑

## 验收标准（Acceptance）

- `python3 -m pytest tests/test_knowledge.py -q` 全部通过（离线、无网络）
- 测试用唯一 `kb-test-*` 前缀写入真实 db，测后清理，不留脏数据
- 既有回归 `python3 -m pytest -q` 不受影响（除既有环境问题用例）
