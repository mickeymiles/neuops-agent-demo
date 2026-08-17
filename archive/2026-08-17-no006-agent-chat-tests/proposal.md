# 变更提案：NO-006 Agent 对话与 MCP 补充测试覆盖

- 编号：`20260817-no006-agent-chat-tests`
- 日期：2026-08-17
- 类型：测试补齐（规格回填闭环）
- 涉及规格：NO-006 Agent 对话与 MCP

## 为什么（Why）

NO-006 Agent 对话（SSE 事件流 / 技能中心）为存量核心功能，
但 `specs/TRACEABILITY.md` 标注其**无测试覆盖**。需补齐单元测试满足
"测试绑定规格（# NO-006 FR-x）"。

## 范围（In / Out of Scope）

- In scope：新增 `tests/test_agent_chat.py`，覆盖 NO-006 的：
  - `sse_event` 事件格式（event/data/空行）
  - `mock_agent_run` 审批确认分支（approved_action）：事件序列与内容（无网络依赖，可离线）
  - 技能中心接口 `GET /api/skills`、`GET /api/skills/full`（字段结构）
- Out of scope：不触碰真实 LLM/9006/9007 调用分支（skill-10/11/12 需真实服务，跳过）；
  不改动 `app/agent_chat.py` 逻辑

## 验收标准（Acceptance）

- `python3 -m pytest tests/test_agent_chat.py -q` 全部通过（离线、无网络）
- 既有回归 `python3 -m pytest -q` 不受影响（除既有环境问题用例）
