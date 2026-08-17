# AGENTS.md — neuops-agent-demo 工程规则

> 本文件为工程级规则，**根级 `../AGENTS.md` 的 SDD 铁律在本工程同样适用且优先**。进入本工程前必读。

## 1. 工程简介

NeuOps 运维监控平台（FastAPI + SQLite + Chroma）。核心能力：多源数据采集（探针）、运维本体与拓扑、告警引擎、Agent 对话（SSE + MCP 工具）、运维一体化门户（11 Tab）、知识库 RAG。

## 2. 代码结构速览

| 目录/文件 | 职责 |
|-----------|------|
| `app/probe/` | 六类数据采集器 + 日志采集 + 调度 |
| `ops_ontology.py` | 运维本体（五类实体三类关系）、拓扑接口 |
| `alert_engine.py` | 告警规则引擎、syslog 噪音排除 |
| `agent_chat.py` | SSE 对话、技能中心 |
| `mcp_tools.py` / `mcp_gateway.py` | MCP 工具与网关 |
| `knowledge.py` | 知识库入库、向量检索、RAG |
| `routes_*.py` | 按域拆分的路由 |
| `static/ops.html` | /ops 一体化平台前端 |
| `tests/` | 测试（3 个文件 32 项） |

## 3. 规格索引（详见 `specs/README.md`）

| 编号 | 模块 | 编号 | 模块 |
|------|------|------|------|
| NO-001 | 数据采集（探针） | NO-006 | Agent 对话与 MCP |
| NO-002 | 运维本体与拓扑 | NO-007 | 运维一体化平台 |
| NO-003 | 告警引擎 | NO-008 | 知识库与 RAG |
| NO-004 | 自愈引擎（已废弃） | NO-005 | 代码修复器（已废弃） |

## 4. 本工程约定

- 规格编号前缀：`NO-`，如 `NO-004 FR-2.1`
- 变更目录：`changes/YYYYMMDD-<slug>/`，模板见 `changes/_template/`
- 归档目录：`archive/YYYY-MM-DD-<slug>/`
- 测试命令：`cd neuops-agent-demo && pytest -q`
- Agent 对话涉及 MCP 工具时，工具契约变化须在 proposal 中列出

## 5. 修改指引

1. 定位涉及模块 → 阅读对应 `specs/<编号>-<module>/spec.md`
2. 按根级 AGENTS.md 的 SDD 铁律建立变更提案
3. 实现时保持与既有规格一致；如需求变化，走 delta 流程
4. 运行 `pytest -q` 回归，更新 `specs/TRACEABILITY.md`
