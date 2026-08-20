# 归档区（Archive）— neuops-agent-demo

> 已完成的变更按 `archive/YYYY-MM-DD-<slug>/` 归档留档。
> 归档时 delta 增量已合并回 `../specs/` 主规格，本目录仅保存变更历史（proposal/design/tasks/delta）。

## 归档记录

| 归档日期 | 变更编号 | 标题 | 涉及规格 |
|----------|----------|------|----------|
| 2026-08-17 | 20260817-no006-agent-chat-tests | NO-006 Agent 对话补充测试覆盖 | NO-006 |
| 2026-08-17 | 20260817-no008-knowledge-tests | NO-008 知识库与 RAG 补充测试覆盖 | NO-008 |
| 2026-08-17 | 20260817-remove-self-heal | 整体移除自愈（NO-004）与代码修复（NO-005）：删除引擎/代码/接口/MCP 工具/incidents 表，同步清理前端、测试与文档，主规格标记已废弃 | NO-004 / NO-005 |
| 2026-08-17 | 20260817-topo-layout-drag | 智能体拓扑拖拽位置持久化与双链路平行布局（kb 对齐 tool、vector_db 对齐 server） | NO-007 |
| 2026-08-17 | 20260817-db-package-refactor | 数据层内部重构：`app/db.py` 拆分为 `app/db/` 包，合并重复 mock 数据源（无行为变更） | — |
| 2026-08-17 | 20260817-bid-expert | 新增 NO-009 投标业务专家能力：投标工作台 + `app/bidding/` 模块 + `bid_projects` 表 + 预置 5 类投标知识库 | NO-009 / NO-006 / NO-008 |
| 2026-08-17 | 20260817-admin-bid-link | 后台管理门户「工作成果」菜单新增投标工作台入口卡片 | NO-009 FR-9 |
| 2026-08-17 | 20260817-bid-multifile-format | 多文件分类解析（categories/独立落盘/来源溯源）、docx 排版基线、格式要求自动提取覆盖 | NO-009 FR-10/11/12 |
| 2026-08-17 | 20260817-bid-template-demo | 投标模板上传/模板化材料生成、技术方案演示网页（自包含 HTML + 截图） | NO-009 FR-13/14/15 |
| 2026-08-17 | 20260817-bid-writeflow | 投标工作台 SOP 化分步编写流程：项目知识库入库、需求分析、假页面、大纲与逐章、左右对照确认、6 步进度与组装 | NO-009 FR-16~21 |
| 2026-08-18 | 20260818-bid-autoflow | 一键智能起草流水线（拆标→需求→假页面→大纲→逐章→截图→组装）+ 横向流程视图 + 截图真插入 | NO-009 FR-22/23 |
| 2026-08-18 | 20260818-remove-todos | 移除工作台"待办任务"菜单及 `/api/todos` 链路（无规格条目） | — |
| 2026-08-18 | 20260818-topo-layer-fix | 智能体拓扑依赖方向修正：MCP 链路 `Skill→MCP Server→Tools`、RAG 链路 `子智能体→向量数据库→知识库`，向量库与 Server 同列、知识库与 Tools 同列 | NO-007 |
| 2026-08-18 | 20260818-application-lsof-fix | 应用采集器 lsof 监听端口解析修复（原 `parts[-1]` 恒为 `(LISTEN)` 致端口发现失效），`test_application_collector` 转通过 | NO-001 |

## 规则

- 归档目录只读，不再修改
- 归档内容与 `specs/` 主规格、`TRACEABILITY.md` 保持同步
- 如需追溯历史决策，查阅对应归档目录
