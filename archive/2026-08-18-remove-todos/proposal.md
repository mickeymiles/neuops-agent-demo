# 提案：工作台页面移除待办任务菜单与相关功能

> 变更编号：`20260818-remove-todos`
> 作者：AI 助手 | 日期：2026-08-18 | 状态：已完成

## 背景与问题

对话工作台（`static/index.html`）左侧导航包含"待办任务"菜单，配套待办列表/历史处理视图、`/api/todos` 与 `/api/todos/history` 接口、`todos` / `todo_history` 数据表及 seed 数据。用户决定不再需要该能力，要求去掉工作台"待办任务"菜单及相关功能。

## 目标

1. 工作台左侧导航不再有"待办任务"菜单项，页面无待办任务/历史处理视图。
2. 后端不再存在 `/api/todos`、`/api/todos/history` 接口及 `todos` / `todo_history` 表相关数据层链路。
3. 帮助文档、CSS、mock 数据、seed、追踪矩阵同步清理；`pytest -q` 全通过。

## 变更范围

### In Scope

- `static/index.html`：删除导航菜单项、`#page-todos` 页面块、`S.showingTodoHistory` 状态、`navigateTo('todos')` 分支、`renderTodos`/`renderTodoItem`/`renderTodoHistory`/`toggleTodoHistory` 函数、init 中 `/api/todos` 角标拉取、待办相关 CSS（保留被数字员工页面复用的 `.todo-empty`）、帮助文档待办章节与提及
- `static/manage.css`：删除待办相关样式块与共享选择器中的 `.todo-item` 引用
- `app/routes_workspace.py`：删除 `/api/todos`、`/api/todos/history` 路由与对应 import
- `app/db/tasks.py`：删除 `db_list_todos`、`db_list_todo_history`
- `app/db/__init__.py`：删除上述两个函数的 re-export
- `app/db/schema.py`：删除 `todos`、`todo_history` 建表
- `app/db/seed.py`：删除 `MOCK_TODOS` / `MOCK_TODO_HISTORY` 的 import 与 seed 插入
- `seed_data.py`、`mock_data.py`：删除 `MOCK_TODOS` / `MOCK_TODO_HISTORY` 定义
- `mcp_gateway.py`：删除未使用的 `MOCK_TODOS` import
- `scripts/split_db.py`：SEED_NAMES 与 tasks 模块符号清单同步删除
- `specs/TRACEABILITY.md`：变更登记追加一行

### Out of Scope

- `app/agent_chat.py` 中"高风险操作转人工"的对话文案（`该变更已登记为待办` 仅对话输出文本，不依赖待办数据链路）
- `README.md` 的"待办（另行安排）"节（泛指后续事项，非本功能）
- 长期任务、数字员工等其余导航功能

## 接口与数据契约

删除的 API：

```text
GET  /api/todos
GET  /api/todos/history
```

删除的表结构（建表语句一并移除，不执行 DROP 保留数据）：

```sql
-- todos / todo_history 建表语句从 schema.py 移除
```

## 涉及规格条目

待办任务功能未在 `specs/` 建立独立规格条目（`specs/README.md` 索引 NO-001~NO-009 无对应模块），本次不涉及主规格 ADDED/MODIFIED/REMOVED，仅需在 `TRACEABILITY.md` 登记变更。

## 验收标准

- [x] `python3 -m py_compile` 全绿；`cd neuops-agent-demo && pytest -q` 全通过
- [x] `grep -rn "待办任务\|page-todos\|/api/todos\|db_list_todos\|todo_history\|MOCK_TODOS"` 无功能代码残留（历史文档示例除外）
- [x] 服务重启后工作台页面无"待办任务"菜单，无 404 报错
- [x] `specs/TRACEABILITY.md` 已更新变更登记

## 风险与兼容性

- `index.html` 的 `.todo-empty` 类被数字员工技能池（`empSkillPool`）与工具列表空态复用，必须保留该 CSS 规则，仅删除其余 `.todo-*` 样式
- 存量数据库中的 `todos` / `todo_history` 表数据不再被读取（无迁移需求）
- 前端若残留对已删接口的调用会导致 404，需同步清理全部相关 JS
