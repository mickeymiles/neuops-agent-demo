# Delta Spec：NO-006 Agent 对话与 MCP（测试覆盖）

> 本 delta 不修改任何既有 Requirement，仅新增测试标准（TC）与测试位置声明。

## ADDED Requirements

### Requirement: Agent 对话测试覆盖

系统 SHALL 为 Agent 对话提供单元测试，覆盖：SSE 事件格式、审批确认分支
（approved_action 事件序列与内容）、技能中心接口字段结构。

#### Scenario: Agent 对话测试全绿

- GIVEN 测试环境（无真实 LLM/9006/9007 服务）
- WHEN 运行 `python3 -m pytest tests/test_agent_chat.py -q`
- THEN 全部用例离线通过

## MODIFIED Requirements

无。

## REMOVED Requirements

无。
