# 任务清单：NO-008 知识库与 RAG 测试

- [x] T1 确认 parse_document / chunk_text / _tokenize_zh / _keyword_search / search_knowledge 真实行为
- [x] T2 编写 `tests/test_knowledge.py`
  - [x] T2.1 用例 1：parse_document（txt/md/xlsx/不支持扩展名）
  - [x] T2.2 用例 2：chunk_text（空/聚合/定长重叠/碎片过滤）
  - [x] T2.3 用例 3：_tokenize_zh（短词/长词窗口）
  - [x] T2.4 用例 4：_keyword_search（打分排序，db 隔离+清理）
  - [x] T2.5 用例 5：search_knowledge（空输入/向量降级关键词）
- [x] T3 运行 `python3 -m pytest tests/test_knowledge.py -q` 通过（离线）
- [x] T4 回归 neuops 既有测试不受影响
- [x] T5 归档 `changes/20260817-no008-knowledge-tests` → `archive/`
- [x] T6 更新 `specs/TRACEABILITY.md`（NO-008 覆盖状态）与 `archive/README.md`
