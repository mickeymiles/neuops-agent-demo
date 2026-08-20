# Tasks：移除工作台待办任务菜单与相关功能

> 变更编号：`20260818-remove-todos`（无对应规格条目，属功能移除）

## 任务清单

### T1 前端 index.html — 导航与页面（# 20260818-remove-todos）

- [x] 删除左侧导航"待办任务"菜单项（含 `todoBadge`）
- [x] 删除 `#page-todos` 页面块（待办列表 + 历史处理视图 + 分组/空态容器）
- [x] 删除 `S` 对象中的 `showingTodoHistory: false` 状态

### T2 前端 index.html — 交互与渲染逻辑

- [x] 删除 `navigateTo` 中 `if (page === 'todos') { S.showingTodoHistory = false; renderTodos(); }` 分支
- [x] 删除 `renderTodos`、`renderTodoItem`、`renderTodoHistory`、`toggleTodoHistory` 函数
- [x] 删除 `init()` 中 `/api/todos` 角标拉取代码块

### T3 前端 index.html — CSS 与帮助文档

- [x] 删除 `.todo-*` 样式块（**保留 `.todo-empty`**，被数字员工技能池/工具空态复用）
- [x] 共享选择器（`.qa-item, .skill-item, .todo-item, .emp-item, .task-item` 等）移除 `.todo-item` 引用
- [x] 帮助文档：删除"📋 待办任务"菜单介绍、整个"六、待办任务"章节、布局表"待办角标"字样、"已实现"清单中的"待办任务"；后续章节序号（七→六、八→七、九→八）顺延

### T4 前端 manage.css

- [x] 删除待办相关样式块（`.todo-*`）
- [x] 共享选择器移除 `.todo-item` 引用

### T5 后端 API

- [x] `app/routes_workspace.py`：删除 `/api/todos`、`/api/todos/history` 路由及 `db_list_todos`/`db_list_todo_history` import

### T6 数据层

- [x] `app/db/tasks.py`：删除 `db_list_todos`、`db_list_todo_history` 函数
- [x] `app/db/__init__.py`：删除两个函数的 re-export
- [x] `app/db/schema.py`：删除 `todos`、`todo_history` 建表
- [x] `app/db/seed.py`：删除 `MOCK_TODOS`/`MOCK_TODO_HISTORY` import 与 seed 插入

### T7 数据与工具脚本

- [x] `seed_data.py`：删除 `MOCK_TODOS`、`MOCK_TODO_HISTORY` 定义
- [x] `mock_data.py`：删除 `MOCK_TODOS` 定义
- [x] `mcp_gateway.py`：删除未使用的 `MOCK_TODOS` import
- [x] `scripts/split_db.py`：SEED_NAMES 与 tasks 模块符号清单同步删除

### T8 验证与追踪

- [x] `python3 -m py_compile` 全绿，`cd neuops-agent-demo && pytest -q` 全通过
- [x] `grep` 确认无功能代码残留
- [x] `specs/TRACEABILITY.md` 追加变更登记

## 验收

- 工作台左侧导航无"待办任务"，无 404 请求
- `pytest -q` 全通过
- `.todo-empty` 样式保留（数字员工页面空态不受影响）
