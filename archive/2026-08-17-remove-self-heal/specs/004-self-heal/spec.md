# Delta：自愈引擎 Specification — REMOVED

> 变更编号：`20260817-remove-self-heal`
> 规格编号：NO-004 | delta 类型：REMOVED

## REMOVED

- Requirement: 自愈状态机（detected → repairing → verifying → recovered）
- Requirement: 动作白名单（restart_service / restart_9006 / recycle_container / cleanup_disk / restore_db / restart_self / code_heal）
- Requirement: 重试与开关控制（self_heal_enabled / self_heal_max_retry）
- Requirement: 修复后健康验证
- Requirement: 动作安全约束
- Requirement: 审计与升级（incidents 记录 + 飞书通知）
- Requirement: 事件查询接口（`GET /api/ops/incidents`、`GET /api/ops/incidents/{incident_id}`）
- NFR-1：单事件自愈全流程 5 分钟内完成
- NFR-2：所有自动动作可追溯、可被人工关闭
- TC-1 / TC-2：测试标准（`tests/test_self_heal.py` 已删除）

## 合并说明

主规格 `specs/004-self-heal/spec.md` 全文删除，状态标记"已废弃"；对应代码 `app/ops_self_heal.py` 与 `tests/test_self_heal.py` 一并删除。
