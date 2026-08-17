# 设计：整体移除自愈（self-heal）与代码修复（code heal）功能

> 变更编号：`20260817-remove-self-heal`
> 日期：2026-08-17 | 状态：已评审

## 技术方案

采用"整链移除、逐层收敛"策略：

1. 先建 SDD 变更提案（本目录）。
2. 自下而上删除核心引擎：删除 `app/ops_self_heal.py` 与 `app/ops_code_heal.py` 整文件。
3. 数据库/告警引擎解耦：`app/db.py` 删除 `incidents` 建表与数据层函数；`app/alert_engine.py::_process_alert_ops` 在告警入库与飞书通知后不再调用 `create_incident_from_alert` / `process_incident`。
4. 路由与 MCP 收敛：`routes_ops.py` 删除 incidents / code-heal 接口与自愈配置项；`routes_monitor.py` 告警详情去掉 incidents 关联；`mcp_gateway.py` 删除 `ops_incidents` 工具、`ops_alerts_aggregate` 去 incidents。
5. 前端 UI 清理：`ops.html` 删除"自愈事件"菜单、事件 Tab、聚合区、相关 JS 与轮询；`monitor.html`/`index.html` 同步清理。
6. 测试与验证：删除自愈/代码修复测试，更新 `test_ops_api.py`，跑 py_compile 与 pytest。
7. 文档与归档：清理 README / AGENTS / specs / docs，全量残留扫描后归档至 `archive/`。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `app/ops_self_heal.py` | 删除整文件（自愈引擎） |
| `app/ops_code_heal.py` | 删除整文件（代码修复器） |
| `app/db.py` | 删除 `incidents` 建表 SQL / CREATE INDEX / `incident_*` 数据层函数 |
| `app/alert_engine.py` | `_process_alert_ops` 切断自愈触发；SUGGESTIONS 去自愈文案；rule-ops-007 desc 改写 |
| `app/feishu_notify.py` | 删除 `notify_incident` |
| `app/config.py` | 删除 `CODE_HEAL_*` 配置 |
| `main.py` | 删除 `get_engine` import / start / stop |
| `app/routes_ops.py` | 删除 incidents / code-heal 路由；SETTINGS_DEF 去自愈项；aggregate 去 incidents；overview 去 incidents 统计 |
| `app/routes_monitor.py` | 告警详情接口删除 incidents 关联返回段 |
| `mcp_gateway.py` | 删除 `ops_incidents`；`ops_alerts_aggregate`/`ops_settings`/`ops_overview` 去自愈内容 |
| `static/ops.html` | 删除自愈菜单、事件 Tab、聚合区、JS 函数、轮询分支 |
| `static/ops.css` | 删除 `.st-*` 事件状态样式与 timeline 状态色 |
| `static/monitor.html` | 删除告警详情抽屉自愈事件区 |
| `static/index.html` | 删除自愈交互说明、MCP 工具表条目、根因分析调用链中的 incidents |
| `tests/test_self_heal.py` | 删除整文件 |
| `tests/test_code_heal.py` | 删除整文件 |
| `tests/test_ops_api.py` | 删除 incidents 相关用例 |
| `README.md` / `AGENTS.md` / `specs/*` / `docs/*` | 同步清理自愈/代码修复条目 |

## 数据模型变更

```sql
-- 移除
DROP TABLE IF EXISTS incidents;
DROP INDEX IF EXISTS idx_incidents_state;
```

不迁移数据（用户确认彻底删除）。

## 兼容性说明

- `GET /api/ops/alerts/aggregate` 响应结构变化（去掉 `incidents`），调用方仅剩前端 `ops.html` 与 MCP `ops_alerts_aggregate`，同步更新。
- `GET /api/ops/settings` 返回的配置项减少（去掉自愈分组），前端配置中心无对应控件，无兼容问题。
- 删除后台 SelfHealEngine 线程不影响告警引擎 `_alert_engine_loop`。
