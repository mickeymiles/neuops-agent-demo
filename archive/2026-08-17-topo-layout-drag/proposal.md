# 提案：智能体拓扑拖拽持久化与双链路布局

> 变更编号：`20260817-topo-layout-drag`
> 作者：AI 助手 | 日期：2026-08-17 | 状态：已批准

## 背景与问题

1. 智能体拓扑已开启 `draggable` / `roam`，但节点拖拽后的新位置无法保存：`setOption(..., true)` 全量重置、30 秒自动刷新、Tab 切换均会重新渲染，拖拽结果随即丢失。
2. 当前布局中 RAG 链路（`agent → kb → vector_db`）被置于最右（88%/96%），其连线横穿 MCP 链路右侧，与 MCP 链（`hub → agent → skill → tool → server`）交叉，视觉混乱。产品定位上知识库对应 MCP Tool、向量数据库对应 MCP Server，是两大核心板块，应平级展示。

## 目标

1. 节点拖拽后的位置 SHALL 持久化：自动刷新、Tab 切换、浏览器重载后均保持不变。
2. 拓扑 SHALL 提供"重置布局"操作，一键清除保存位置并恢复默认布局。
3. 布局 SHALL 调整为双链路平行：知识库与 Tools 同列、向量数据库与 MCP Server 同列，MCP 链在上、RAG 链在下，连线不交叉。

## 变更范围

### In Scope

- `static/monitor.html`：
  - 拖拽位置持久化（dragend 事件 + localStorage，按节点 id 存取）
  - 渲染时优先读取已保存位置，未拖拽节点走默认布局
  - 面板头部新增「↺ 重置布局」按钮
  - `LAYER_X` / y 分带布局调整（kb 对齐 tool、vector_db 对齐 server，上下两排平行）
- 规格：`specs/007-ops-page/spec.md` 追加拓扑交互与布局两条 Requirement（delta 流程）

### Out of Scope

- 后端接口与数据库：无改动（拓扑数据层级本就平行，纯前端布局问题）
- 位置存服务端/多端同步：仅本地 localStorage 持久化
- 拓扑缩放（roam）状态保存：仅保存节点坐标

## 接口与数据契约

无后端接口变更。前端新增 localStorage key（按节点 id 存坐标）：

```json
{
  "neuops.topo.pos.v1": {
    "hub": { "x": 120, "y": 310 },
    "emp_2": { "x": 300, "y": 180 }
  }
}
```

## 涉及规格条目

- `NO-007` ADDED：`Requirement: 智能体拓扑交互`（拖拽持久化 + 重置）
- `NO-007` ADDED：`Requirement: 拓扑双链路布局`（kb/tool、vector_db/server 同列平行）

## 验收标准

- [ ] 拖拽节点后，30 秒自动刷新 / 切换 Tab / 刷新浏览器，位置均保持
- [ ] 点击「重置布局」后，所有节点恢复默认分层布局
- [ ] 拓扑渲染后 MCP 链与 RAG 链上下分带、同列对齐，连线无交叉
- [ ] `pytest -q` 全量回归通过

## 风险与兼容性

- 节点 id 稳定性：id 均来自数据库主键或固定值（`hub`），拖拽持久化 key 安全
- localStorage 不可用（隐私模式）时降级为仅本次会话内有效，不影响功能
- 窗口尺寸变化可能使保存的绝对像素坐标偏移，提供「重置布局」兜底
- 纯前端改动，不影响后端接口与数据
