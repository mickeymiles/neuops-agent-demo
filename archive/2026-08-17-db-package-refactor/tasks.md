# 任务清单：数据层 `app/db.py` 拆分 + mock_data 去重

> 变更编号：`2026-08-17-db-package-refactor`

## 前置

- [x] 人工评审 proposal 与 design（纯内部重构，无 delta specs）

## 实现

- [x] [P0] 编写 AST 拆分脚本 `scripts/split_db.py`（域映射 + 引用分析 + re-export 生成）
- [x] [P0] 运行脚本生成 `app/db/` 包八模块与 `__init__.py`，删除 `app/db.py`
- [x] [P0] 消除 `mock_data.py` 同名冲突：`app/mcp_tools.py` 改导入 → 删除 `app/mock_data.py`

## 测试

- [x] 冒烟：`python -c "from app import db; from app.db import init_session_db, db_list_employees, _query_rows"` 通过
- [x] 全量回归：`cd neuops-agent-demo && pytest -q` 通过

## 收尾

- [x] 更新 `specs/TRACEABILITY.md` 变更登记
- [x] 归档：变更目录移入 `archive/2026-08-17-db-package-refactor/`
