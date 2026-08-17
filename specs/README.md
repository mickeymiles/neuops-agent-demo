# 规格库（Specs）— neuops-agent-demo

> 本目录是 neuops-agent-demo 系统行为规范的**单一事实源**（Single Source of Truth）。
> 遵循 OpenSpec（Fission-AI 开源 SDD 框架）规范模型：
> `## Purpose`（能力解决什么问题）+ `### Requirement: xxx`（SHALL/MUST/SHOULD，RFC 2119）+ `#### Scenario: xxx`（GIVEN/WHEN/THEN 可验证场景）。

## 规格索引

| 编号 | 模块 | 状态 | 最后更新 | 对应代码/文档 |
|------|------|------|----------|----------------|
| NO-001 | 数据采集（探针） | 生效 | 2026-08-17 | `app/probe/` |
| NO-002 | 运维本体与拓扑 | 生效 | 2026-08-17 | `app/ops_ontology.py` |
| NO-003 | 告警引擎 | 生效 | 2026-08-17 | `app/alert_engine.py` |
| NO-004 | 自愈引擎 | 已废弃 | 2026-08-17 | 已整体移除（20260817-remove-self-heal） |
| NO-005 | 代码修复器 | 已废弃 | 2026-08-17 | 已整体移除（20260817-remove-self-heal） |
| NO-006 | Agent 对话与 MCP | 生效 | 2026-08-17 | `app/agent_chat.py`、`app/mcp_tools.py` |
| NO-007 | 运维一体化平台 | 生效 | 2026-08-17 | `app/routes_ops.py`、`static/ops.html` |
| NO-008 | 知识库与 RAG | 生效 | 2026-08-17 | `app/knowledge.py` |
| NO-009 | 投标业务专家能力 | 生效 | 2026-08-17 | `app/bidding/`、`static/bidding.html` |

## 状态定义

- **规划中**：模块已列入规格计划，尚未回填
- **回填中**：正在依据存量代码提炼行为规格
- **生效**：规格已与代码行为对齐，作为开发契约
- **已废弃**：该功能已被移除或合并，规格仅作历史参考

## 规范约定

- 规格是**行为合同**，不是实现说明书：类名、框架选型、具体文件路径不写入 spec.md
- 需求语气词遵循 RFC 2119：`SHALL`（必须）/ `MUST`（绝对要求）/ `SHOULD`（建议）
- 每个 Requirement 至少配一个 GIVEN/WHEN/THEN Scenario
- 需求编号：`FR-x`（功能需求）、`NFR-x`（非功能需求）、`TC-x`（测试标准）
- 规格变更必须走 `changes/` 提案流程，delta 合并回本目录，禁止直接改主规格

## 追踪

规格 ↔ 代码 ↔ 测试的映射见 [TRACEABILITY.md](./TRACEABILITY.md)（规格回填完成后维护）。
