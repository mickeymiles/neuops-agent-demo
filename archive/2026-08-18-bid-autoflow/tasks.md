# 任务：投标智能起草全流程编排

> 变更编号：`20260817-bid-autoflow` | 规格：NO-009 FR-15/18/20/21/22/23

## 后端

- [ ] T1 新增 `run_bid_pipeline()` 编排函数与进度表（bid_engine.py）        # NO-009 FR-22
- [ ] T2 新增 `get_pipeline_status()`（bid_engine.py）                      # NO-009 FR-22
- [ ] T3 新增 playwright 截图模块 `app/bidding/screenshot.py`               # NO-009 FR-15
- [ ] T4 mockup LLM 提示词升级为直出完整 HTML（_llm_mockup_html）           # NO-009 FR-18
- [ ] T5 组装 md 引用截图、docx `_add_demo_shot_table` 真插入图片           # NO-009 FR-15
- [ ] T6 新增路由 `/pipeline/run`、`/pipeline/status`（routes_bidding.py）  # NO-009 FR-22
- [ ] T7 requirements.txt 追加 playwright

## 前端

- [ ] T8 bidding.html：顶部两上传卡片 + 「开始生成」主按钮                 # NO-009 FR-23
- [ ] T9 横向步骤条 + 内容面板横向滑动（scroll-snap + scrollTo）           # NO-009 FR-23
- [ ] T10 逐章面板保留左右对照复核；移除「快捷生成」；合规自检并入组装面板 # NO-009 FR-20/21

## 测试与文档

- [ ] T11 新增 test_bid_pipeline_run / auto_confirm / without_files / screenshot_embed
- [ ] T12 更新 specs/TRACEABILITY.md 与 specs/README.md 状态索引
- [ ] T13 全量 pytest -q 回归通过（既有 33 例不回归）
- [ ] T14 归档：变更目录移入 archive/，delta 合并回主规格

## 验收（对齐 proposal）

- [ ] 一键生成自动完成 6 阶段并停在复核；auto_confirm 全自动完成组装+自检+导出
- [ ] 前端步骤条自动横向滑动；demo 为 LLM 直出 HTML；docx 含真实截图（无浏览器降级占位）
