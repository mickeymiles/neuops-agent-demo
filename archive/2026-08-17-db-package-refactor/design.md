# 设计：数据层 `app/db.py` 按表域拆分为包

> 变更编号：`2026-08-17-db-package-refactor`
> 日期：2026-08-17 | 状态：已评审

## 技术方案

采用 **AST 机械拆分脚本**（`scripts/split_db.py`），按顶层符号归属切分，避免 2056 行手工搬运出错：

1. 解析 `app/db.py` 顶层符号 → 建立 `name → (起始行, 结束行)` 映射。
2. 按"域 → 符号清单"映射表，将每个域的代码块提取为独立模块文件。
3. 对每个域做 **AST 引用分析**，自动生成精准 imports：
   - 标准库（json / sqlite3 / threading / uuid / datetime）按引用交集导入；
   - `seed_data` 10 个种子符号按引用交集导入；
   - `base` 域符号按引用交集导入（`from .base import ...`）；
   - `DB_PATH` 引用时 `from ..config import DB_PATH`；
   - 跨域引用检测（如某域用到他域符号）时追加 `from .<other> import ...`。
4. 生成 `__init__.py`：按原文件顺序 re-export **全部**顶层符号，保证三种外部导入方式零改动兼容。

依赖方向单向：`base`（无包内依赖）→ 其余七域（仅依赖 `base` + 标准库 + seed_data/config），无循环导入。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `app/db.py` | 删除（拆分为包后移除） |
| `app/db/__init__.py` | 新增：统一 re-export 全部符号（含私有辅助） |
| `app/db/base.py` | 新增：`_db_lock` / `_get_conn` / `_ensure_column` / `_query_rows` / `_query_one` / `_est_tokens` / `_text_summary` / `_agent_name_map` / `_parse_route` / `_COST_*` |
| `app/db/schema.py` | 新增：`init_session_db` / `init_config_db`（建表） |
| `app/db/sessions.py` | 新增：会话/项目/分享/历史/`seed_mock_conversations` |
| `app/db/seed.py` | 新增：`seed_config_db` / `sync_seed_employees` / `ensure_mcp_server_mapping` + MCP CRUD |
| `app/db/employees.py` | 新增：员工/技能 CRUD |
| `app/db/tasks.py` | 新增：长任务/待办/后台任务 |
| `app/db/kb.py` | 新增：知识库 CRUD 与员工绑定（命名 `kb` 避开与 `app/knowledge.py` 混淆） |
| `app/db/ops.py` | 新增：`OPS_ENTITY_TYPES` / `init_ops_db` / settings / 指标 / 日志 / 实体 / 关系 |
| `app/mcp_tools.py` | 修改：`from .mock_data import ...` → `from mock_data import ...`（根数据源） |
| `app/mock_data.py` | 删除（合并至根 `mock_data.py`，内容一致且已含时间戳工具函数） |
| `scripts/split_db.py` | 新增：AST 机械拆分脚本（一次性工具） |
| `specs/TRACEABILITY.md` | 修改：变更登记 |

## 数据模型变更

无。不触碰任何 DDL / 表结构 / 种子数据内容。

## 备选方案

- **手工复制拆分**：2056 行易出错、难以评审，弃用。
- **按行号硬切（sed/awk）**：边界依赖行号漂移，且不做 import 分析，弃用。
- **保留单文件仅改 mock_data**：未解决 db.py 膨胀问题，与既有 `split_refactor.py` 方向不符，弃用。

## 兼容性说明

- 外部导入面：`from app import db` / `from . import db` / `from .db import x` 三种方式在 `app/db/` 包 + `__init__.py` re-export 下全部兼容。
- `app/routes_monitor.py` 直接导入的私有辅助（`_query_rows` 等 10 个符号）在 `__init__.py` 中显式 re-export。
- `main.py` 导入的 `init_*` / `seed_*` 符号同样 re-export。
- mock 数据源合并后，`MOCK_ALARMS/CHANGES/CMDB/LOGS/METRICS` 5 个符号在根 `mock_data.py` 中已存在且内容一致（`MOCK_KNOWLEDGE` 经核实为死代码，无引用）。
