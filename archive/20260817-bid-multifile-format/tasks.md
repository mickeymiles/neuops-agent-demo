# 任务清单：20260817-bid-multifile-format

- [x] 1. 变更提案与 delta 规格（proposal.md / specs/ / design.md / tasks.md）
- [x] 2. `app/bidding/bid_engine.py`：分类常量 / auto_category / _read_extracted_text 改造 / format_spec 提取与存储 / docx 排版渲染
- [x] 3. `app/bidding/routes_bidding.py`：upload 支持 categories 参数 + 分类落盘 + _list_files 返回分类
- [x] 4. `static/bidding.html`：上传分类选择、文件分类标签、格式规范展示
- [x] 5. `tests/test_bid.py`：新增 FR-10 / FR-11 / FR-12 测试（标注规格编号）
- [x] 6. 运行 `pytest -q` 全量验证（既有 + 新增）：`tests/test_bid.py` 19/19 通过
- [x] 7. 更新 `specs/TRACEABILITY.md` 映射
