# 变更提案：应用采集器 lsof 监听端口解析修复

> 变更编号：`20260818-application-lsof-fix`
> 作者：AI 助手 | 日期：2026-08-18 | 状态：已完成

## 背景与问题

- `app/probe/application_collector.py::_discover_listen_ports` 的 lsof 通道以 `parts[-1]`（NAME 列最后一段，恒为 `(LISTEN)`）作为端口提取源，
  正则 `:(\d+)\s*$` 永远匹配失败，导致 lsof 通道永远发现不了任何监听端口。
- macOS 非 root 用户下 psutil 兜底通道受权限限制看不到其他进程监听连接 → 双通道全失效，
  应用采集恒为空。`tests/test_ops_collector.py::test_application_collector` 因此长期失败，
  TRACEABILITY 曾误记为"9007 服务未运行"环境依赖（实际 9007 服务运行同样失败）。

## 变更内容

- [x] MODIFIED `app/probe/application_collector.py`：端口从整行提取（正则锚定行尾 `:(\d+)\s*(?:\(LISTEN\))?\s*$`，兼容 IPv4 `*:9007 (LISTEN)` 与 IPv6 `[::]:9007`），进程名仍取 COMMAND 列

## 影响范围

- 探针应用采集（NO-001）：本机监听端口应用实体将恢复发现；`test_application_collector` 通过
- 不影响 9007 服务启动本身（服务已正常运行）

## 验收标准

- [x] `lsof` 通道能解析 `TCP *:9007 (LISTEN)` 为 9007 端口，进程名取 COMMAND 列
- [x] 9007 服务运行时 `ApplicationCollector().collect()` 返回含 `neuops-agent` 的实体
- [x] `tests/test_ops_collector.py::test_application_collector` 通过；全量回归无新失败
