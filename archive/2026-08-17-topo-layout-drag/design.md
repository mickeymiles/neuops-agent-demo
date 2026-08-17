# 设计：智能体拓扑拖拽持久化与双链路布局

> 变更编号：`20260817-topo-layout-drag`
> 日期：2026-08-17 | 状态：已评审

## 技术方案

### 1. 拖拽位置持久化（纯前端）

- 监听 ECharts graph 的 `dragend` 事件，取 `p.data.x / p.data.y`（渲染坐标系像素），按节点 `id` 存入 `localStorage`（key：`neuops.topo.pos.v1`）。
- `renderTopo` 构建节点时优先读取已保存坐标：有则直接用，无则走默认布局。这样 `setOption(notMerge=true)`、30 秒自动刷新、Tab 切换、浏览器重载都能保持。
- 面板头部新增「↺ 重置布局」按钮：清除 localStorage 并重新加载拓扑。

### 2. 双链路平行布局

- `LAYER_X` 调整：`kb` 从 88% → 52%（与 `tool` 同列）、`vector_db` 从 96% → 60%（与 `server` 同列）。
- 新增 `Y_BAND` 纵向分带：`hub` 居中带 [30,70]，`agent` 全高带 [12,88]（连通上下两链），MCP 链 `skill/tool/server` 上半带 [4,48]，RAG 链 `kb/vector_db` 下半带 [52,96]。同带内多节点按实际数量均匀分布（与现逻辑一致）。
- 已保存位置的节点跳过默认布局，避免被覆盖。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `static/monitor.html` | 拓扑面板 head 加重置按钮；`LAYER_X`/`Y_BAND` 常量；`renderTopo` 读取保存坐标 + dragend 保存；y 分带排布 |
| `specs/007-ops-page/spec.md` | ADDED 两条 Requirement（拓扑交互、双链路布局） |
| `specs/TRACEABILITY.md` | NO-007 行补充 monitor.html、变更登记 |

## 数据模型变更

无（localStorage 前端私有数据，不进数据库）。

## 备选方案

- 拖拽保存到后端数据库：可实现多端同步，但引入接口/表变更，本次无必要，Out of Scope。
- 保存相对百分比坐标：窗口 resize 自适应更好，但小屏下精度差且需处理缩放坐标系换算，选择绝对像素 + 重置兜底。

## 兼容性说明

- 后端接口与数据零改动。
- 旧数据无 `neuops.topo.pos.v1` key，首次渲染全部走默认布局。
- localStorage 异常（隐私模式/禁用）时 try/catch 降级，仅影响持久化不阻塞渲染。
