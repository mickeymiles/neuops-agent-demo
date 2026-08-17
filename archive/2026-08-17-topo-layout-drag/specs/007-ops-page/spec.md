# Delta：NO-007 运维一体化平台（智能体拓扑）

> 目标规格：`specs/007-ops-page/spec.md`
> 变更编号：`20260817-topo-layout-drag`
> 类型：ADDED

## ADDED

### Requirement: 智能体拓扑交互

系统 SHALL 在"智能体监控"的智能体拓扑视图中支持节点拖拽与位置持久化：用户拖拽节点到新位置后，系统 SHALL 保存该位置，并在自动刷新、Tab 切换与浏览器重载后保持节点位于新位置；系统 SHALL 提供"重置布局"操作，SHALL 清除已保存位置并恢复默认布局。

#### Scenario: 拖拽并持久化节点位置

- GIVEN 用户处于智能体拓扑视图
- WHEN 用户将某节点拖拽到新位置
- THEN 节点显示在新位置
- AND 30 秒自动刷新、切换 Tab 或重载页面后，该节点仍位于新位置

#### Scenario: 重置布局

- GIVEN 用户已拖拽调整过部分节点位置
- WHEN 用户点击"重置布局"
- THEN 所有节点恢复默认分层布局
- AND 再次刷新后节点仍为默认布局

### Requirement: 拓扑双链路布局

系统 SHALL 在智能体拓扑视图中以两条上下分带、相互平行的链路展示依赖关系：MCP 链路（总智能体 → 子智能体 → Skill → Tools → MCP Server）SHALL 展示于上半区，RAG 链路（子智能体 → 知识库 → 向量数据库）SHALL 展示于下半区；知识库 SHALL 与 Tools 同列对齐、向量数据库 SHALL 与 MCP Server 同列对齐，两条链路的连线 SHALL 不相互交叉。

#### Scenario: 双链路平行排布

- GIVEN 拓扑数据同时包含 MCP 依赖与 RAG 依赖
- WHEN 渲染智能体拓扑
- THEN 知识库节点与 Tools 节点位于同一列、向量数据库节点与 MCP Server 节点位于同一列
- AND MCP 链路节点位于上半区、RAG 链路节点位于下半区，两组连线互不交叉
