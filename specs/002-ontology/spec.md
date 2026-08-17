# 运维本体与拓扑 Specification

> 规格编号: NO-002 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `app/ops_ontology.py`

## Purpose

以运维本体模型（六类实体、三类关系）组织监控数据，提供实体查询、关系查询与拓扑图构建能力，为一体化监控与智能体拓扑提供统一数据视图。

## Requirements

### Requirement: 六类实体模型

系统 SHALL 定义六类实体：server（服务器）、database（数据库）、network（网络）、container（容器）、middleware（中间件）、application（应用），每类实体 SHALL 携带唯一标识、名称、类型与状态属性。

#### Scenario: 实体建模

- GIVEN 探针采集到一台服务器
- WHEN 该服务器入库
- THEN 实体以 server 类型存储，状态与指标可被查询

### Requirement: 三类关系模型

系统 SHALL 定义三类关系：`runs_on`（运行在）、`hosted_on`（部署于）、`connects_to`（连接至），用于表达实体间的部署与依赖关系。

#### Scenario: 部署关系

- GIVEN 应用 A 部署在服务器 S 上，数据库 D 运行在服务器 S 上
- WHEN 构建关系图
- THEN 生成 runs_on（A→S、D→S）关系边

### Requirement: 实体与关系元数据

系统 SHALL 为实体、关系、状态维护元数据（展示标签、图标、配色），支撑前端统一样式渲染。

#### Scenario: 元数据渲染

- GIVEN 前端渲染 server 类型实体
- WHEN 使用本体元数据
- THEN 展示 server 对应的图标与状态配色

### Requirement: 全局拓扑构建

系统 SHALL 依据实体与关系构建全局拓扑（build_topology），输出 ECharts graph 格式的 nodes、edges、summary 与 meta，支持前端 2D/3D 视图渲染。

#### Scenario: 全局拓扑

- GIVEN 系统中存在多台服务器、数据库与应用及其关系
- WHEN 调用拓扑构建
- THEN 输出完整节点列表、关系边列表与汇总统计

### Requirement: 单实体子图

系统 SHALL 支持构建单实体一跳子图（build_entity_graph），返回指定实体及其直接关联实体与关系，便于聚焦排查。

#### Scenario: 单实体聚焦

- GIVEN 实体"应用 A"关联服务器 S 与数据库 D
- WHEN 构建实体 A 的子图
- THEN 子图仅含 A、S、D 及三者间关系

### Requirement: 查询接口

系统 SHALL 提供实体列表（`GET /api/ops/entities`）、实体详情（`GET /api/ops/entities/{entity_id}`）与拓扑（`GET /api/ops/topology`）接口。

#### Scenario: 查询拓扑

- GIVEN 前端打开本体拓扑 Tab
- WHEN 调用 `GET /api/ops/topology`
- THEN 返回拓扑图数据并完成渲染

## 非功能需求

- NFR-1：拓扑接口 SHALL 在 3 秒内返回（万级节点）
- NFR-2：关系数据 SHALL 随实体采集增量维护，不要求手工录入

## 测试标准

- TC-1：实体/关系建模与拓扑构建用例（对应 FR-1~FR-4），位置 `tests/test_ontology.py`
- TC-2：查询接口用例（对应 FR-6）
