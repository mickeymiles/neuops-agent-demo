# 任务清单：数字员工业务工作台

> 变更编号：`20260820-employee-workbench`

## 前置

- [x] 更新 delta 规格 `specs/010-employee-workbench/spec.md`
- [x] 明确首版范围与后续对话调整边界

## 实现

- [x] [P0] 增加员工工作台配置迁移、序列化和校验（NO-010 FR-2）
- [x] [P0] 增加详情工作台 Tab 与差异化渲染（NO-010 FR-1）
- [x] [P1] 增加配置编辑和恢复默认（NO-010 FR-2）

## 测试

- [x] 补充工作台 API 测试（5 项通过）
- [ ] 全量回归：`pytest -q`（49 项通过；既有 macOS 应用端口发现测试 1 项失败）

## 收尾

- [x] 更新 `specs/TRACEABILITY.md`
- [ ] 功能验收后归档并合并主规格
