# 任务清单：应用采集器 lsof 监听端口解析修复

> 变更编号：`20260818-application-lsof-fix`

## 修复

- [x] `app/probe/application_collector.py::_discover_listen_ports`：端口提取由 `parts[-1]` 改为整行正则
      `re.search(r":(\d+)\s*(?:\(LISTEN\))?\s*$", line)`，进程名仍取 `parts[0]`（COMMAND）

## 测试

- [x] `pytest tests/test_ops_collector.py::test_application_collector` 通过（9007 服务运行中）
- [x] 全量回归：`pytest -q` 无新失败

## 收尾

- [x] 更新 `specs/TRACEABILITY.md`（修正 test_application_collector 失败归因）
- [x] 归档：`archive/2026-08-18-application-lsof-fix/`
