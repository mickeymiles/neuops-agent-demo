# 数据采集（探针）Specification

> 规格编号: NO-001 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `app/probe/`（六类采集器 + 日志采集 + 调度器）

## Purpose

通过统一探针框架周期性采集六类运维实体（服务器、容器、数据库、中间件、应用、网络）的运行状态与统一日志，入库供告警、拓扑与展示消费，并支持手动触发与远程上报。

## Requirements

### Requirement: 六类实体采集

系统 SHALL 提供六类实体采集器：服务器（CPU/内存/磁盘/进程）、容器（状态/资源/健康）、数据库（连接/慢查询/状态）、中间件（实例/队列/健康）、应用（进程/接口/健康）、网络（接口/流量/连通性），每类采集器 SHALL 产出结构化指标并写入对应实体表。

#### Scenario: 服务器采集

- GIVEN 探针周期性运行
- WHEN 服务器采集器执行
- THEN 服务器实体表的 CPU、内存、磁盘指标被更新

### Requirement: 日志采集

系统 SHALL 提供统一日志采集器，采集应用与系统日志（level、source、message、时间），支持按源（如 `app:` 前缀）区分，供告警引擎统计错误窗口。

#### Scenario: 应用错误日志入库

- GIVEN 应用产生一条 error 级别日志，源为 `app:9007`
- WHEN 日志采集器执行
- THEN 该日志入库，且可被 `count_logs(minutes, level=error, source_prefix=app:)` 统计到

### Requirement: 调度管理

系统 SHALL 提供调度器（ProbeManager）：`run_once` 立即全量采集；`start` 以配置周期启动后台循环采集；`stop` 停止循环。采集周期 SHALL 来自系统配置。

#### Scenario: 周期采集

- GIVEN 配置采集周期为 60 秒
- WHEN 调度器 start
- THEN 每 60 秒执行一轮全量采集，直到 stop

### Requirement: 采集失败隔离

系统 SHALL 隔离单类采集器失败：某类采集器异常 SHALL 不影响其他采集器执行，且 SHALL 记录该类采集器的 last_error 供状态查询。

#### Scenario: 部分采集失败

- GIVEN 数据库采集器连接失败
- WHEN 执行一轮全量采集
- THEN 服务器/容器等其他采集器仍正常入库，数据库采集器状态标记失败及原因

### Requirement: 数据过期清理

系统 SHALL 按天清理超期采集数据，避免指标数据无限增长。

#### Scenario: 清理过期数据

- GIVEN 系统保留窗口为 N 天
- WHEN 触发清理
- THEN N 天前的采集数据被删除

### Requirement: 探针状态与手动触发

系统 SHALL 提供探针状态查询（`GET /api/ops/probe/status`）、手动立即采集（`POST /api/ops/probe/run-now`）与数据上报（`POST /api/ops/probe/ingest`，供远程/CLI 探针上报数据）。

#### Scenario: 手动触发采集

- GIVEN 用户需要立即刷新数据
- WHEN 调用 run-now
- THEN 立即执行一轮全量采集并更新状态

## 非功能需求

- NFR-1：单轮全量采集 SHALL 在 30 秒内完成（万级实体）
- NFR-2：采集器 SHALL 具备超时保护，单类采集不阻塞整体调度

## 测试标准

- TC-1：六类采集与入库用例（对应 FR-1~FR-2），位置 `tests/test_probe.py`
- TC-2：调度启停与失败隔离用例（对应 FR-3~FR-4）
