# 运维一体化平台 Specification

> 规格编号: NO-007 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `app/routes_ops.py`、`static/ops.html`

## Purpose

提供 `/ops` 一体化运维门户，以多 Tab 组织总览、一体化监控、智能体监控、采控中心、告警、拓扑、配置等能力，聚合全部运维模块的实时数据与操作入口。

## Requirements

### Requirement: 门户入口

系统 SHALL 提供 `/ops` 门户页面（`GET /api/ops/page` 返回页面数据），浏览器访问可加载完整运维界面。

#### Scenario: 打开门户

- GIVEN 用户访问 /ops
- WHEN 页面加载
- THEN 门户渲染各 Tab 导航与默认"总览"页

### Requirement: Tab 导航结构

系统 SHALL 提供 10 个主 Tab：总览、一体化监控、智能体监控、采控中心、告警列表、告警规则、本体拓扑、配置中心、智能体、链路追踪；切换 Tab SHALL 展示对应页面。

#### Scenario: Tab 切换

- GIVEN 用户点击"告警列表"
- WHEN 切换 Tab
- THEN 展示告警列表页并加载告警数据

### Requirement: 一体化监控

系统 SHALL 在"一体化监控"Tab 内提供 7 个子视图：服务器、数据库、网络、容器、中间件、应用、统一日志，各视图展示对应实体的实时状态与指标表。

#### Scenario: 服务器视图

- GIVEN 用户切换到一体化监控的服务器子视图
- THEN 展示服务器实体列表（CPU/内存/磁盘/状态）

### Requirement: 智能体监控

系统 SHALL 在"智能体监控"Tab 内提供子视图：总览、全部智能体、智能体拓扑、链路追踪，并支持按时间范围（近 7/14/30 天）筛选。

#### Scenario: 时间范围筛选

- GIVEN 用户选择"近 30 天"
- WHEN 查看智能体总览
- THEN 指标按近 30 天窗口统计展示

### Requirement: 采控中心

系统 SHALL 在"采控中心"Tab 内提供"采集情况"（各类采集器运行状态、数据量）与"采集配置"（周期等参数）两个子视图。

#### Scenario: 采集情况

- GIVEN 用户打开采控中心
- THEN 展示各采集器最近采集时间、状态与错误信息

### Requirement: 告警视图

系统 SHALL 提供告警列表（含聚合接口 `GET /api/ops/alerts/aggregate`）与告警规则管理视图，展示告警的最新状态。

#### Scenario: 告警聚合

- GIVEN 存在多条告警
- WHEN 调用聚合接口
- THEN 返回按严重度/类型聚合的告警统计供告警列表页展示

### Requirement: 配置中心

系统 SHALL 提供配置中心：查看与更新系统设置（`GET/PUT /api/ops/settings`），设置变更 SHALL 持久化并即时生效。

#### Scenario: 更新设置

- GIVEN 用户修改采集周期配置
- WHEN 保存
- THEN 配置持久化且后续采集按新周期执行

### Requirement: 数据查询接口

系统 SHALL 为门户提供统一数据接口：概览（`GET /api/ops/overview`）、指标（`GET /api/ops/metrics`）、日志（`GET /api/ops/logs`）、实体与拓扑等。

#### Scenario: 总览加载

- GIVEN 用户打开门户
- THEN 页面并行调用概览与指标接口渲染总览卡片

## 非功能需求

- NFR-1：门户页面首屏加载 SHALL 在 3 秒内完成
- NFR-2：接口失败 SHALL 不影响页面其他模块展示（局部降级）

## 测试标准

- TC-1：Tab 结构与数据接口用例（对应 FR-1~FR-3、FR-8），位置 `tests/test_ops_page.py`
- TC-2：配置读写用例（对应 FR-7）
