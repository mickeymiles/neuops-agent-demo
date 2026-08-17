# 提案：整体移除自愈（self-heal）与代码修复（code heal）功能

> 变更编号：`20260817-remove-self-heal`
> 作者：AI 助手 | 日期：2026-08-17 | 状态：已批准

## 背景与问题

NeuOps 运维平台当前包含"自愈（self-heal）"功能：告警引擎在 ops 告警入库后自动创建自愈事件（incident），由 `SelfHealEngine` 后台线程按状态机驱动"检测 → 修复 → 验证 → 恢复"，并联动代码修复（code heal）流水线。用户决定不再需要该能力：要求去掉前端"自愈事件"菜单，并将整体工程中与自愈相关的功能全部去除。

自愈与代码修复深度耦合（共用 `incidents` 表、状态机、settings 开关、飞书通知），无法独立保留，故一并移除整条链路。

## 目标

1. 前端 `/ops` 侧边栏不再有"自愈事件"菜单，页面无任何自愈/代码修复区块与按钮。
2. 后端不再存在自愈引擎、代码修复器、incidents 数据链路及对应 API / MCP 工具；告警链路保留"告警入库 → 飞书通知 → 告警查询/统计"。
3. 数据库 `incidents` 表结构、数据层函数与数据彻底删除；README / specs / docs / tests 同步清理并归档。

## 变更范围

### In Scope

- 删除 `app/ops_self_heal.py`、`app/ops_code_heal.py`、`tests/test_self_heal.py`、`tests/test_code_heal.py`
- `app/db.py`：删除 `incidents` 建表 SQL 与 `incident_*` 数据层函数
- `app/alert_engine.py`：`_process_alert_ops` 切断自愈触发，保留告警入库与飞书告警；调整自愈相关建议文案
- `app/feishu_notify.py`：删除 `notify_incident`
- `app/config.py`：删除 `CODE_HEAL_*` 配置
- `main.py`：不再导入/启动/停止自愈引擎
- `app/routes_ops.py`：删除 incidents / code-heal 接口与自愈配置项，`alerts/aggregate` 仅返回 alerts，`overview` 去掉 incidents 统计
- `app/routes_monitor.py`：告警详情接口去掉自愈事件关联段
- `mcp_gateway.py`：删除 `ops_incidents` 工具，`ops_alerts_aggregate`/`ops_settings`/`ops_overview` 去掉自愈相关内容
- `static/ops.html` / `ops.css`：删除自愈菜单、事件 Tab、聚合区、JS 函数、状态样式与轮询分支
- `static/monitor.html`：删除告警详情抽屉自愈事件区
- `static/index.html`：删除自愈交互说明与 MCP 工具表条目
- 测试、README、AGENTS.md、specs、docs 同步清理；按 SDD 流程归档

### Out of Scope

- `app/probe/*` 的 health 指标采集（属监控数据，非自愈）
- `rule-ops-007` 日志错误突增告警规则本身、`/monitor` 重定向、`seed_alert_rules()`、`init_ops_db()` 主流程
- `changes/README.md` 中 `20260817-fix-heal-guard` 变更规范示例（保留为格式参考）
- 存量 `alerts` 表及其数据（告警功能保留）

## 接口与数据契约

删除的 API：

```text
GET  /api/ops/incidents
GET  /api/ops/incidents/{incident_id}
POST /api/ops/code-heal/run
GET  /api/ops/code-heal/status
```

删除的 MCP 工具：

```text
POST/GET /tools/ops_incidents
```

数据契约变更：

```sql
DROP TABLE IF EXISTS incidents;  -- 建表语句与数据层函数一并移除
```

`GET /api/ops/alerts/aggregate` 响应不再包含 `incidents` 字段，仅保留 `alerts` 聚合统计。

## 涉及规格条目

- `NO-004`（自愈引擎）：REMOVED
- `NO-005`（代码修复器）：REMOVED
- `NO-007`（运维一体化平台）：MODIFIED（`/api/ops/alerts/aggregate` 不再含 incidents；侧边栏无自愈事件菜单）

## 验收标准

- [ ] `python3 -m py_compile` 全绿；`pytest -q` 全通过
- [ ] 服务重启后 `/ops` 与 `/api/monitor/*` 返回 200，日志无 error/traceback
- [ ] `GET /api/ops/settings` 不再返回自愈/代码修复开关项
- [ ] MCP 工具列表无 `ops_incidents`；数据库中无 `incidents` 表
- [ ] `/ops` 侧边栏无"自愈事件"菜单，页面无自愈区块/按钮；告警详情无自愈事件抽屉
- [ ] 全工程 grep `自愈|incident|self_heal|code_heal|heal` 无功能代码残留（历史文档示例除外）
- [ ] `specs/TRACEABILITY.md` 已更新，变更目录已归档至 `archive/`

## 风险与兼容性

- 真实环境存在历史 incidents 数据，本次按用户确认**彻底删除**（不迁移、不保留备份表）
- 前端若残留对已删接口的调用会导致 404：需同步清理 `ops.html`/`monitor.html`/`index.html` 中所有相关 JS
- `ops_alerts_aggregate` MCP 工具保留但去掉 incidents 字段，Agent 对话侧引用链需同步更新（`index.html` 流程说明）
- 删除 `get_engine().start()` 后后台线程减少，不影响告警引擎主循环
