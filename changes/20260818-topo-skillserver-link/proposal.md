# 变更提案：拓扑 MCP 链路 skill→server→tool 逐级连线 + 选中节点关联子图高亮

> 变更编号：`20260818-topo-skillserver-link`
> 作者：AI 助手 | 日期：2026-08-18 | 状态：草稿

## 背景与问题

1. **MCP 链路缺 skill → server 边**：`skill_mcp.mcp_id` 指向 `mcp_tools.id`（seed 中 `tools` 为工具 id 列表），
   后端直接生成 `skill → tool`（type=tool）边；同时 `server → tool`（type=server）边存在，
   导致渲染中 skill 未先连 server，链路为 `skill → tool` 与 `server → tool` 并行，非规格要求的
   `Skill → MCP Server → Tools` 逐级串接。
2. **选中节点高亮范围过窄**：`emphasis.focus: "adjacency"` 仅高亮直接相邻节点（前后一层），
   用户期望"有关联关系的都高亮"——即沿边可达的整个连通子图（含间接关联节点与连线）。

## 变更内容

- [x] MODIFIED `app/routes_monitor.py`：`skill_mcp` 边改为 `skill → server`（经 `mcp_tools.server_id`
      归一到所属 Server，按 (skill,server) 去重），边 type=`mcp`、label=调用；`server → tool` 边保留，
      MCP 链路完整为 `hub → agent → skill → server → tool`
- [x] MODIFIED `static/ops.html`：
      - `AG_EDGE_COLOR` 增 `mcp`、详情面板 `relTypeName` 增 `调用 MCP`
      - 高亮改为选中节点关联连通子图：新增 `AG_topoReachable`（无向 BFS 可达集）与
        `AG_applyTopoFocus`（相关节点/边高亮、无关淡化），`emphasis.focus` 改 `self`；
        点击节点聚焦、点击空白恢复
- [x] MODIFIED `specs/007-ops-page/spec.md`：拓扑双链路布局 Requirement 明确
      Skill → MCP Server → Tools 逐级连线，新增"选中节点高亮全部关联"Scenario

## 影响范围

- NO-007 智能体拓扑（后端 `/api/monitor/topology` 边集合、前端 ops.html 拓扑视图）
- `tests/test_ops_api.py` 新增断言，既有拓扑方向断言不受影响

## 验收标准

- [ ] `/api/monitor/topology` 中 MCP 调用边为 `skill → server`，且不存在 `skill → tool` 直达边；
      `server → tool` 承载边保留
- [ ] 前端选中任一节点，沿边可达的全部节点与连线高亮、其余淡化；点击空白恢复全亮
- [ ] `pytest -q` 全量回归通过
