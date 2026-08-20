# 任务清单：智能体拓扑依赖方向修正

> 变更编号：`20260818-topo-layer-fix`

## 前置

- [x] 人工评审 proposal（用户确认修正方向：MCP Server 承载 Tools、向量数据库承载知识库）

## 实现

- [x] [P0] `app/routes_monitor.py`：`/api/monitor/topology` 边方向修正——`tool → server` 改为 `server → tool`（MCP Server 承载 Tools）、`agent → kb → chroma` 改为 `agent → chroma → kb`（数字员工检索向量库、向量库承载知识库，员工边去重）（对应 `NO-007 拓扑双链路布局`）
- [x] [P0] `static/ops.html`：`AG_LAYER_X` 列交换（server/vector_db 同列 45%、tool/kb 同列 58%）、`AG_CAT_INDEX` 顺序、拖拽位置 key 升级 v3、详情弹窗关系文案调整（对应 `NO-007 拓扑双链路布局`）

## 规格

- [x] 更新 delta 规格 `specs/007-ops-page/spec.md`（MODIFIED「拓扑双链路布局」Requirement 依赖方向）

## 测试

- [x] 新增 `tests/test_ops_api.py::test_monitor_topology_layer_direction`（`/api/monitor/topology` 依赖方向断言，标注 `# NO-007`）
- [x] 全量回归：`cd neuops-agent-demo && pytest -q`

## 收尾

- [x] 更新 `specs/TRACEABILITY.md` 追踪矩阵
- [x] 归档：变更目录移入 `archive/2026-08-18-topo-layer-fix/`，delta 合并回 `specs/007-ops-page/spec.md`
