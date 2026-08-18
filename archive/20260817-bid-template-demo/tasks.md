# 任务清单：20260817-bid-template-demo

- [x] 1. 变更提案与 delta 规格（proposal.md / specs/ / design.md / tasks.md）
- [x] 2. `static/demo-preview.html`：高保真演示原型落盘（独立可预览）+ playwright 截图验证
- [x] 3. `app/bidding/bid_engine.py`：模板解析/保存删除、`_norm_title`、`_render_docx_with_template` 模板化导出
- [x] 4. `app/bidding/bid_engine.py`：`_demo_features` / `_build_demo_html` / `DOC_TYPES+tech_demo` / html 与 docx 导出扩展
- [x] 5. `app/bidding/routes_bidding.py`：/template 上传删除、project.template、export fmt=html
- [x] 6. `static/bidding.html`：三列一行上传、模板卡片、demo 生成按钮、成果预览/下载 html
- [x] 7. `tests/test_bid.py`：新增 FR-13/14/15 测试（标注规格编号，no_llm fixture 禁用外部 LLM）
- [x] 8. 运行 `pytest -q` 全量验证（既有 + 新增）
- [x] 9. 合并 delta 规格到 `specs/009-bid-expert/spec.md`、归档到 `archive/`、更新 `specs/TRACEABILITY.md`
