# Delta：代码修复器 Specification — REMOVED

> 变更编号：`20260817-remove-self-heal`
> 规格编号：NO-005 | delta 类型：REMOVED

## REMOVED

- Requirement: 修复流水线（detected → diagnosing → fixing → testing → deploying → verifying → recovered）
- Requirement: 补丁白名单路径
- Requirement: 补丁格式约束
- Requirement: 修改前备份与回滚
- Requirement: 测试门禁
- Requirement: 规则修复器（RULE_FIXERS）
- Requirement: 审计与升级（fix_log + 飞书通知）
- Requirement: 修复接口（`POST /api/ops/code-heal/run`、`GET /api/ops/code-heal/status`）
- NFR-1：单次修复流水线 10 分钟内完成
- NFR-2：任何自动文件变更可回滚、可审计
- TC-1 / TC-2：测试标准（`tests/test_code_heal.py` 已删除）

## 合并说明

主规格 `specs/005-code-heal/spec.md` 全文删除，状态标记"已废弃"；对应代码 `app/ops_code_heal.py` 与 `tests/test_code_heal.py` 一并删除。
