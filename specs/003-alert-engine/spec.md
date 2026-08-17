# 告警引擎 Specification

> 规格编号: NO-003 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `app/alert_engine.py`

## Purpose

基于统一探针指标与日志，按告警规则周期性扫描并产生/解除告警，排除系统日志噪音，为告警列表提供告警事实与处置建议。

## Requirements

### Requirement: 告警规则模型

系统 SHALL 支持告警规则字段：name（规则名）、metric（监控指标）、target（目标实体）、threshold（阈值）、window_min（统计窗口分钟）、severity（严重级）、type（告警类型）、desc（描述）。

#### Scenario: 规则字段

- GIVEN 一条 CPU 使用率告警规则
- WHEN 查看规则详情
- THEN 规则包含 metric=cpu_usage、threshold=90、severity=critical、type=perf 等字段

### Requirement: 默认规则集

系统 SHALL 内置默认规则集（LLM 规则 5 条 + 运维规则 7 条），覆盖常见故障/性能/可用性场景；初始化时 SHALL 幂等写入（seed），不覆盖用户已修改的规则配置。

#### Scenario: 幂等初始化

- GIVEN 用户已自定义某条规则
- WHEN 系统再次执行规则初始化
- THEN 该用户自定义配置保持不变

### Requirement: 告警扫描与产生

系统 SHALL 按规则周期性扫描：对指标类规则统计窗口内指标值，对日志类规则统计窗口内 error 日志数，超过阈值 SHALL 产生告警；指标恢复正常后 SHALL 自动解除告警。

#### Scenario: 阈值触发

- GIVEN CPU 使用率规则阈值为 90%
- WHEN 窗口内 CPU 使用率连续超过 90%
- THEN 产生一条 critical/perf 告警

### Requirement: Syslog 噪音排除

系统 SHALL 在日志类告警统计中排除系统日志噪音：仅统计应用日志源（`app:` 前缀），系统日志（`system` 源）SHALL 不计入错误窗口统计，避免误报。

#### Scenario: 排除系统日志

- GIVEN 窗口内 system 源有 500 条 error 日志，app:9007 源有 3 条 error 日志
- WHEN 按规则统计错误日志数（阈值 5）
- THEN 仅统计 app 源 3 条，未达阈值，不产生告警

### Requirement: 告警等级与类型

系统 SHALL 支持三级严重度（critical / warning / info）与多类告警类型（fault 故障、perf 性能、prewarn 预警、availability 可用性、business 业务）。

#### Scenario: 严重度分级

- GIVEN 服务不可用与磁盘水位偏高两类告警
- THEN 服务不可用为 critical（availability），磁盘水位偏高为 warning（prewarn）

### Requirement: 处置建议

系统 SHALL 为告警提供处置建议：优先按指标匹配建议（SUGGESTION_BY_METRIC），未命中时回退到告警类型级建议（SUGGESTIONS）。

#### Scenario: 建议回退

- GIVEN 某指标无专属建议
- WHEN 生成告警
- THEN 使用其告警类型（如 perf）对应的通用建议

### Requirement: 规则管理接口

系统 SHALL 提供告警规则的查询（`GET /api/ops/alert-rules`）、新增（`POST`）、更新（`PUT /{rule_id}`）与删除（`DELETE /{rule_id}`）能力，规则变更 SHALL 持久化。

#### Scenario: 新增规则

- GIVEN 用户新增一条内存告警规则
- WHEN 保存
- THEN 规则持久化并参与后续扫描

## 非功能需求

- NFR-1：单轮规则扫描 SHALL 在 10 秒内完成（百条规则级）
- NFR-2：告警产生与解除 SHALL 具备去重，同一状态不重复产生

## 测试标准

- TC-1：规则扫描与阈值判定用例（对应 FR-3），位置 `tests/test_alert_engine.py`
- TC-2：syslog 噪音排除用例（对应 FR-4）
