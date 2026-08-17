# Agent 对话与 MCP Specification

> 规格编号: NO-006 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `app/agent_chat.py`、`app/mcp_tools.py`、`app/mcp_gateway.py`、`app/devtools.py`

## Purpose

提供基于 SSE 的 Agent 对话能力：支持定向技能模式、真实调用业务系统（如 9006 合同比对）、MCP 工具与开发工具调用，并在"写操作/高危变更"上坚持"AI 只研判不擅自变更、转人工执行"的安全原则。

## Requirements

### Requirement: SSE 对话流

系统 SHALL 通过 SSE 推送渐进式对话事件流：`agent_thought`（思考过程）→ `tool_call`（工具调用，如适用）→ `agent_message`（最终回答，可含 actions 建议）→ `message_end`（会话收尾）。

#### Scenario: 流式对话

- GIVEN 用户发起一条查询
- WHEN 对话执行
- THEN 客户端按序收到 thought、tool_call（如涉及）、message、message_end 事件

### Requirement: 定向技能模式

系统 SHALL 支持按技能定向执行：用户选择特定技能（如采购清单比对 skill-10）时，Agent 按该技能的既定流程执行并真实调用目标系统数据。

#### Scenario: 采购比对技能

- GIVEN 用户选择「采购清单比对」技能并询问雷神项目
- WHEN 对话执行
- THEN Agent 连接 9006 合同比对系统，查询合同列表、匹配目标合同并返回比对结果

### Requirement: 高风险操作转人工

系统 SHALL 遵循权限安全规范：AI 不自动执行任何写操作/高危变更；当用户确认执行此类操作时，SHALL 将变更登记为待办并提示运维人员手动执行，同时提供业务系统入口链接。

#### Scenario: 变更待人工执行

- GIVEN 用户确认执行某重启操作
- WHEN Agent 收到人工确认
- THEN Agent 输出"变更待人工执行"表格与打开运维平台的链接，不自动执行

### Requirement: MCP 工具调用

系统 SHALL 支持通过 MCP 工具调用外部能力，工具清单、服务器配置 SHALL 可查询（db_get_mcp_tool / db_get_mcp_server），工具执行结果 SHALL 反馈到对话流。

#### Scenario: 调用 MCP 工具

- GIVEN 用户询问某 MCP 能力
- WHEN Agent 路由到对应 MCP 工具
- THEN 工具被调用且结果以 tool_call 事件反馈

### Requirement: 开发工具执行

系统 SHALL 提供开发工具集（DEV_TOOLS），通过 execute_dev_tool 执行，并对大结果做摘要（_tool_result_summary）控制上下文。

#### Scenario: 结果摘要

- GIVEN 工具返回超长结果
- WHEN 反馈到对话
- THEN 结果被截断为摘要并提示存在省略

### Requirement: 会话与历史

系统 SHALL 维护会话（ensure_conversation）与消息持久化（save_user_message / save_agent_message），支持多员工、多会话隔离。

#### Scenario: 会话持久化

- GIVEN 用户完成一段对话
- WHEN 刷新页面再次进入
- THEN 历史消息可从数据库恢复

### Requirement: 成本统计

系统 SHALL 按输入/输出 token 单价（_COST_INPUT_PER_M / _COST_OUTPUT_PER_M）统计 Agent 调用成本。

#### Scenario: 成本记录

- GIVEN 完成一次模型调用
- THEN 输入/输出 token 及折算成本被记录

### Requirement: emp-007 重操作跳转工作台

系统 SHALL 使售前投标专家（emp-007）在聊天中区分两类请求：信息类问答 SHALL 在聊天内基于绑定知识库回答；上传规范书、拆标、生成应答、合规自检、导出文档等重操作请求，SHALL 输出引导语并附投标工作台链接（`http://127.0.0.1:9007/bidding`），SHALL NOT 在聊天内执行重操作。

#### Scenario: 聊天内引导跳转

- GIVEN 用户向 emp-007 提出重操作请求（如"帮我拆标""生成投标应答"）
- WHEN 对话执行
- THEN emp-007 回复跳转指引与工作台链接，说明工作台内已支持的操作，不在聊天内执行

#### Scenario: 聊天内信息问答

- GIVEN 用户向 emp-007 提出信息类问题（资质要求、评分标准解读、中标经验）
- WHEN 对话执行
- THEN emp-007 基于绑定知识库在聊天内直接回答

## 非功能需求

- NFR-1：SSE 首包响应 SHALL 在 3 秒内到达
- NFR-2：对话消息 SHALL 持久化，服务重启后不丢失

## 测试标准

- TC-1：SSE 事件流与技能模式用例（对应 FR-1~FR-2），位置 `tests/test_agent_chat.py`
- TC-2：高风险操作转人工用例（对应 FR-3）
