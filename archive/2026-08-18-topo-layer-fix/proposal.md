# 提案：智能体拓扑依赖方向修正（MCP Server 承载 Tools / 向量数据库承载知识库）

> 变更编号：`20260818-topo-layer-fix`
> 作者：AI 助手 | 日期：2026-08-18 | 状态：已完成

## 背景与问题

1. 智能体监控 → 智能体拓扑 中，MCP 与 RAG 两条链路的**依赖方向与层级**存在逻辑错误：
   - 当前 MCP 链路为 `Skill → Tools → MCP Server`（Tools 在上游），实际应为 `Skill → MCP Server → Tools`（MCP Server 承载 Tools）。
   - 当前 RAG 链路为 `数字员工 → 知识库 → 向量数据库`（知识库在上游），实际应为 `数字员工 → 向量数据库 → 知识库`（向量数据库承载知识库）。
2. 用户明确要求：**向量数据库与 MCP Server 同级对齐、知识库与 Tools 同级对齐**；即 `MCP Server` 与 `向量数据库` 同列（均为第二级依赖）、`Tools` 与 `知识库` 同列（均为第三级叶节点）。

## 目标

1. MCP 链路依赖方向 SHALL 为 `总智能体 → 子智能体 → Skill → MCP Server → Tools`。
2. RAG 链路依赖方向 SHALL 为 `总智能体 → 子智能体 → 向量数据库 → 知识库`。
3. 布局列 SHALL 保持 向量数据库 与 MCP Server 同列、知识库 与 Tools 同列。

## 变更范围

### In Scope

- `app/routes_monitor.py`：`/api/monitor/topology` 边方向修正
  - `tool → server` 改为 `server → tool`（MCP Server 承载工具）
  - `agent → kb → chroma` 改为 `agent → chroma → kb`（数字员工检索向量库、向量库承载知识库，员工边去重）
- `static/ops.html`：`AG_LAYER_X` 列交换（server/vector_db 同列 45%、tool/kb 同列 58%），`AG_CAT_INDEX` 顺序、拖拽位置 key 升级 v3、详情弹窗关系文案调整
- 规格：`specs/007-ops-page/spec.md`「拓扑双链路布局」Requirement 按 delta 更新依赖方向
- 测试：`tests/test_ops_api.py` 新增 `/api/monitor/topology` 依赖方向断言

### Out of Scope

- 拓扑数据源与数据库结构：无改动
- 节点样式 / 颜色 / 拖拽逻辑：无改动（仅列位与边方向）

## 接口与数据契约

无接口变更（`/api/monitor/topology` 响应结构不变，仅 edges 的 source/target 方向变化）：

```json
{
  "edges": [
    { "source": "<server_id>", "target": "<tool_id>", "type": "server", "label": "承载" },
    { "source": "<employee_id>", "target": "chroma", "type": "kb", "label": "检索" },
    { "source": "chroma", "target": "<kb_id>", "type": "vector", "label": "承载" }
  ]
}
```

## 涉及规格条目

- `NO-007` MODIFIED：`Requirement: 拓扑双链路布局`（MCP 链方向 `Skill→MCP Server→Tools`、RAG 链方向 `子智能体→向量数据库→知识库`）

## 验收标准

- [x] `/api/monitor/topology` 返回边方向：`server → tool`、`agent → chroma`、`chroma → kb`，无旧方向边
- [x] 拓扑渲染后 向量数据库 与 MCP Server 同列、知识库 与 Tools 同列
- [x] `pytest -q` 全量回归通过

## 风险与兼容性

- 拖拽持久化 key 由 v2 升级为 v3：旧保存坐标作废（布局参数已变更），用户可一键重置
- 边方向变化仅影响拓扑可视化与详情弹窗文案，不影响业务数据
- 知识库/向量库为空时保持空数据兼容（现有分支逻辑不变）
