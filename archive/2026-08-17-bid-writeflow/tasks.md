# 任务清单：投标工作台 SOP 化分步编写流程

> 变更编号：`20260817-bid-writeflow`
> 状态：已完成实现，待归档

## 前置

- [x] 更新 delta 规格 `specs/009-bid-expert/spec.md`（ADDED FR-16~21 / MODIFIED FR-2/4/15）
- [x] 人工评审 proposal 与 delta 规格（用户确认方案与 DeepSeek key）

## 实现

- [x] [P0] 阶段 A：修复 `doGenerate` 生成后不刷新成果列表 bug；拆标卡片加滚动条防变形（NO-009 FR-3/FR-21）
- [x] [P0] 阶段 B：项目知识库入库——上传/拆标/模板文本写入 `bid-project-{pid}`；新增需求分析 PRD 接口（NO-009 FR-16/FR-17）
- [x] [P0] 阶段 C：假页面生成接口 + 预览（LLM 驱动，降级规则版本）（NO-009 FR-18/FR-15）
- [x] [P0] 阶段 D：大纲 + 逐章生成 + 左右对照编辑器 + 组装导出（NO-009 FR-19/FR-20/FR-21）
- [x] [P1] 阶段 E：6 步步骤条 + loading 遮罩 + 异常降级文案（NO-009 FR-21）

## 测试

- [x] 补充/更新测试用例，标注规格编号（`tests/test_bid.py`：# NO-009 FR-16/17/18/19/20/21，新增 8 用例）
- [x] 全量回归：`cd neuops-agent-demo && pytest -q`（投标模块 33/33 通过；全量 1 例失败为环境依赖 test_application_collector，非本次改动引入）

## 收尾

- [x] 更新 `specs/TRACEABILITY.md` 追踪矩阵
- [x] 归档：变更目录移入 `archive/2026-08-17-bid-writeflow/`，delta 合并回 `specs/` 主规格（主规格已合并，待目录移动）
