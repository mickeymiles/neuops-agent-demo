# Delta Spec：NO-006 Agent 对话与 MCP（emp-007 工作台跳转指引）

> 本 delta 追加一条 Requirement：emp-007 的"信息问答 vs 重操作跳转"行为边界。

## ADDED Requirements

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

## MODIFIED Requirements

无。

## REMOVED Requirements

无。
