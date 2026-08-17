# 任务清单：智能体拓扑拖拽持久化与双链路布局

> 变更编号：`20260817-topo-layout-drag`

## 前置

- [x] 更新 delta 规格 `changes/20260817-topo-layout-drag/specs/007-ops-page/spec.md`（ADDED）
- [x] 人工评审 proposal 与 delta 规格

## 实现

- [x] [P0] `static/monitor.html`：拖拽位置持久化（dragend → localStorage，渲染时优先读取）（对应 `NO-007 智能体拓扑交互`）
- [x] [P0] `static/monitor.html`：面板头部新增「↺ 重置布局」按钮（对应 `NO-007 智能体拓扑交互`）
- [x] [P0] `static/monitor.html`：双链路平行布局（`LAYER_X` kb/vector_db 对齐 tool/server，`Y_BAND` 上下分带）（对应 `NO-007 拓扑双链路布局`）

## 测试

- [x] 全量回归：`cd neuops-agent-demo && pytest -q`
- [x] 浏览器手动验证：拖拽 → 刷新保持、重置恢复、两链无交叉

## 收尾

- [x] 更新 `specs/TRACEABILITY.md` 追踪矩阵
- [x] 归档：变更目录移入 `archive/2026-08-17-topo-layout-drag/`，delta 合并回 `specs/007-ops-page/spec.md`
