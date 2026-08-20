# 任务清单：拓扑 MCP 链路 skill→server→tool 逐级连线 + 关联子图高亮

> 变更编号：`20260818-topo-skillserver-link`

## 实现

- [ ] [P0] `app/routes_monitor.py`：`skill_mcp` 边 `skill → tool` 改为 `skill → server`
      （经 `mcp_tools.server_id` 归一、按 (skill,server) 去重），边 type=`mcp`、label=调用
- [ ] [P0] `static/ops.html`：
      - `AG_EDGE_COLOR` 增 `mcp: "#4f8cff"`；`relTypeName` 增 `mcp: "调用 MCP"`
      - 新增 `AG_topoReachable`（无向 BFS 可达集）与 `AG_applyTopoFocus`（相关高亮/无关淡化）
      - `emphasis.focus: "adjacency"` 改 `"self"`；点击节点聚焦 + 打开详情、点击空白恢复

## 测试

- [ ] 扩展 `tests/test_ops_api.py`：断言 MCP 调用边为 `skill → server`、不存在 `skill → tool` 直达边
- [ ] `pytest -q` 全量回归通过

## 规格

- [ ] `specs/007-ops-page/spec.md`：拓扑双链路布局 Requirement 明确 Skill → MCP Server → Tools
      逐级连线，新增选中节点高亮关联子图 Scenario

## 收尾

- [ ] 更新 `specs/TRACEABILITY.md` 追踪矩阵
- [ ] 归档：`archive/2026-08-18-topo-skillserver-link/`
