# Delta：NO-007 运维一体化平台（拓扑双链路布局依赖方向修正）

> 目标规格：`specs/007-ops-page/spec.md`
> 变更编号：`20260818-topo-layer-fix`
> 类型：MODIFIED

## MODIFIED

### Requirement: 拓扑双链路布局

系统 SHALL 在智能体拓扑视图中以两条上下分带、相互平行的链路展示依赖关系：MCP 链路（总智能体 → 子智能体 → Skill → MCP Server → Tools）SHALL 展示于上半区，RAG 链路（子智能体 → 向量数据库 → 知识库）SHALL 展示于下半区；知识库 SHALL 与 Tools 同列对齐、向量数据库 SHALL 与 MCP Server 同列对齐，两条链路的连线 SHALL 不相互交叉。

#### Scenario: 双链路平行排布

- GIVEN 拓扑数据同时包含 MCP 依赖与 RAG 依赖
- WHEN 渲染智能体拓扑
- THEN 知识库节点与 Tools 节点位于同一列、向量数据库节点与 MCP Server 节点位于同一列
- AND MCP 链路节点位于上半区、RAG 链路节点位于下半区，两组连线互不交叉
- AND MCP 链路依赖方向为 Skill → MCP Server → Tools（MCP Server 承载 Tools）
- AND RAG 链路依赖方向为子智能体 → 向量数据库 → 知识库（向量数据库承载知识库）
