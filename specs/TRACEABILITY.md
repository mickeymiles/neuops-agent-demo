# 追踪矩阵（TRACEABILITY）— neuops-agent-demo

> 规格编号 → 代码文件 → 测试用例 的三向映射，验证"每个规格都有实现、每个实现都有测试"。
> 维护规则：新增/修改规格或测试后必须同步更新本表；后续新增测试用例请在用例处标注规格编号（如 `# NO-004 FR-1`）。

## 映射矩阵

| 规格编号 | 模块 | 代码文件 | 测试用例 |
|----------|------|----------|----------|
| NO-001 | 数据采集（探针） | `app/probe/` | `tests/test_ops_collector.py`（test_base_collector_abstract / test_server_collector / test_database_collector / test_middleware_collector / test_network_collector / test_application_collector / test_container_collector_graceful）、`tests/test_log_collector.py`（test_classify_level / test_tail_reader_incremental / test_log_collector_collect / test_ops_logs_db_roundtrip）、`tests/test_ops_api.py::test_ops_probe_status`、`test_ops_probe_run_now` |
| NO-002 | 运维本体与拓扑 | `app/ops_ontology.py` | `tests/test_ops_api.py::test_ops_entities`、`test_ops_topology` |
| NO-003 | 告警引擎 | `app/alert_engine.py` | `tests/test_ops_api.py::test_ops_alert_rules`、`test_ops_alerts_aggregate` |
| NO-004 | 自愈引擎（已废弃） | （已删除） | （已删除） |
| NO-005 | 代码修复器（已废弃） | （已删除） | （已删除） |
| NO-006 | Agent 对话与 MCP | `app/agent_chat.py`、`app/mcp_tools.py`、`app/mcp_gateway.py` | `tests/test_agent_chat.py`（test_sse_event_format / test_sse_event_data_json_parseable / test_mock_agent_run_approved_action_sequence / test_mock_agent_run_approved_action_thought / test_mock_agent_run_approved_action_message / test_mock_agent_run_approved_action_end / test_skills_api / test_skills_full_api） |
| NO-007 | 运维一体化平台 | `app/routes_ops.py`、`static/ops.html`、`static/monitor.html`（拓扑拖拽持久化 / 双链路布局） | `tests/test_ops_api.py`（test_ops_page / test_ops_overview / test_ops_settings_roundtrip / test_ops_metrics_query / test_ops_alert_rules / test_ops_alerts_aggregate / test_monitor_redirect_to_ops） |
| NO-008 | 知识库与 RAG | `app/knowledge.py` | `tests/test_knowledge.py`（test_parse_document_txt / test_parse_document_md / test_parse_document_xlsx / test_parse_document_unsupported_extension / test_chunk_text_empty / test_chunk_text_short_paras_aggregated / test_chunk_text_long_split_with_overlap / test_chunk_text_short_fragments_filtered / test_tokenize_zh_short_word / test_tokenize_zh_long_word_window / test_tokenize_zh_punctuation_split / test_keyword_search_ranking / test_keyword_search_no_match / test_search_knowledge_empty_input / test_search_knowledge_fallback_keyword） |
| NO-009 | 投标业务专家能力 | `app/bidding/routes_bidding.py`、`app/bidding/bid_engine.py`、`app/db/bidding.py`、`static/bidding.html`、`app/seed_bid_kb.py` | `tests/test_bid.py`（test_bid_project_crud / test_bid_project_name_required / test_bid_upload_txt / test_bid_upload_unsupported_ext / test_bid_parse_rule_fallback / test_bid_parse_api_flow / test_bid_generate_docs / test_bid_generate_invalid_type / test_bid_check_compliance / test_bid_export_md / test_bid_export_docx / test_bid_employee_prompt_guidance / test_bidding_page / test_bid_kb_seeded_and_bound） |

## 覆盖情况统计

- 已回填规格：9 个（NO-001 ~ NO-009）
- 有测试覆盖：7 个（NO-001/002/003/006/007/008/009）
- 已废弃：2 个（NO-004 自愈引擎、NO-005 代码修复器，随功能整体移除）
- 待补测试：无

## 变更登记

| 日期 | 变更编号 | 说明 |
|------|----------|------|
| 2026-08-17 | （规格回填） | 依据存量代码回填 8 个规格并建立本矩阵 |
| 2026-08-17 | 20260817-no006-agent-chat-tests | 新增 NO-006 Agent 对话测试（SSE 格式/审批转人工/技能接口），归档于 archive/2026-08-17-no006-agent-chat-tests/ |
| 2026-08-17 | 20260817-no008-knowledge-tests | 新增 NO-008 知识库测试（解析/切块/分词/关键词降级检索），归档于 archive/2026-08-17-no008-knowledge-tests/ |
| 2026-08-17 | 20260817-remove-self-heal | 整体移除自愈（NO-004）与代码修复（NO-005）功能：删除引擎/代码/接口/MCP 工具/incidents 表，同步清理前端、测试与文档 |
| 2026-08-17 | 20260817-topo-layout-drag | 智能体拓扑拖拽位置持久化（localStorage + 重置布局）与双链路平行布局（kb 对齐 tool、vector_db 对齐 server），NO-007 追加两条 Requirement，归档于 archive/2026-08-17-topo-layout-drag/ |
| 2026-08-17 | 20260817-db-package-refactor | 数据层内部重构（无行为变更）：`app/db.py` 按表域拆分为 `app/db/` 包（base/schema/sessions/seed/employees/tasks/kb/ops + `__init__.py` 全量 re-export，外部导入零改动）；合并重复 mock 数据源（删除 `app/mock_data.py`，`app/mcp_tools.py` 改用根 `mock_data.py`）。44/45 测试通过，1 例失败为环境依赖（本机未运行 neuops 服务，`test_application_collector` 扫不到应用实体）。归档于 archive/2026-08-17-db-package-refactor/ |
| 2026-08-17 | 20260817-bid-expert | 新增 NO-009 投标业务专家能力：投标工作台（`/bidding`，项目 CRUD/上传/拆标/生成/自检/导出）+ `app/bidding/` 模块 + `bid_projects` 表；emp-007 聊天重操作跳转工作台（NO-006 追加 FR）；预置 5 类投标知识库并绑定 emp-007（NO-008 追加 FR）。14 个新用例全通过；既有 1 例失败为环境依赖（`test_application_collector`）。归档于 archive/2026-08-17-bid-expert/ |
