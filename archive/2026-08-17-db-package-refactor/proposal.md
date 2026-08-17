# 提案：数据层 `app/db.py` 按表域拆分为包 + 消除 `mock_data.py` 同名冲突

> 变更编号：`2026-08-17-db-package-refactor`
> 作者：CodeBuddy | 日期：2026-08-17 | 状态：已批准

## 背景与问题

1. `app/db.py` 已膨胀至 2056 行、130+ 顶层符号，混装八大表域（基础设施 / 建表 / 会话 / 配置种子+MCP / 员工技能 / 任务 / 知识库 / 运维监控）。单文件不利于定位、评审与并行开发。
2. 仓库同时存在两个同名模块：根 `mock_data.py` 与 `app/mock_data.py`。两者内容高度重复，仅 `app/` 侧被 `app/mcp_tools.py` 引用，易造成导入歧义与数据分叉。
3. 已存在 `scripts/split_refactor.py` 历史拆分脚本（未落地），说明拆分方向此前已有共识。

## 目标

- [x] `app/db.py` → `app/db/` 包：按表域拆分，**对外零改动**（`from app import db` / `from . import db` / `from .db import x` 三种既有导入方式全部兼容）。
- [x] 消除同名冲突：`app/mock_data.py` 合并入根 `mock_data.py` 后删除，仅保留一份数据源。
- [x] 全量测试通过，行为不变。

## 变更范围

### In Scope

- `app/db.py` 按域拆分为 `app/db/` 包（`base` / `schema` / `sessions` / `seed` / `employees` / `tasks` / `kb` / `ops` 八模块 + `__init__.py` 统一 re-export）。
- 删除 `app/db.py`。
- `app/mcp_tools.py` 的 mock 导入改为指向根 `mock_data.py`；删除 `app/mock_data.py`。
- 更新 `specs/TRACEABILITY.md` 变更登记。

### Out of Scope

- 不改变任何表结构、SQL、函数签名与路由行为。
- 不迁移 `scripts/split_refactor.py`（历史脚本，非本次产出）。
- 不为拆包引入 ORM 或新的依赖。

## 接口与数据契约

无接口与数据契约变更。唯一"契约"是 Python 导入面：

```python
# 以下三种既有写法在拆包后均保持可用
from app import db                 # db.init_session_db() 等
from . import db                   # app 内部模块的既有写法
from app.db import init_session_db # 或 from .db import ...
```

## 涉及规格条目

- 无 FR/NFR 规格条目变更：本变更为纯内部实现结构调整，行为契约（spec.md）不受影响。
- 依据 AGENTS.md 例外条款，纯内部重构不新增 delta specs；完成后登记 TRACEABILITY。

## 验收标准

- [ ] `cd neuops-agent-demo && pytest -q` 全量通过（含既有用例）。
- [ ] 冒烟：`python -c "from app import db; from app.db import init_session_db, db_list_employees, _query_rows"` 无报错。
- [ ] `app/mock_data.py` 已删除，全仓库无 `app.mock_data` 残留引用。
- [ ] 仓库仅剩根 `mock_data.py` 一份 mock 数据源。

## 风险与兼容性

- **re-export 遗漏风险**：`__init__.py` 必须覆盖全部 130+ 顶层符号（含 `_query_*` 等私有辅助，`routes_monitor.py` 直接导入）。由 AST 脚本按符号清单全量生成，并以冒烟测试兜底。
- **循环导入风险**：依赖方向单向（`base` 无依赖，其余域仅依赖 `base` 与 seed_data/config），脚本做跨域引用检测，无循环。
- **行尾差异**：源文件为 CRLF，脚本统一剥离 `\r`，不改变语义。
