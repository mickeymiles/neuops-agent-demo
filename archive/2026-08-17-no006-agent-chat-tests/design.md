# 设计：NO-006 Agent 对话与 MCP 测试

## 被测对象

- `app/agent_chat.py`：
  - `sse_event(event, data)` → `f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"`
  - `mock_agent_run(query, mode, selected_skill, approved_action=None, history=None, conversation_id=None)`：
    async generator，`approved_action` 非空时走"变更待人工执行"分支（纯本地，无网络），
    yield 三个事件：`agent_thought`（确认文案）→ `agent_message`（含 content/actions）→ `message_end`（conversation_id）
- `app/routes_workspace.py`：
  - `GET /api/skills`：技能列表（id/name/desc/category/tags/enabled/group）
  - `GET /api/skills/full`：技能完整信息

## 测试策略

- `mock_agent_run` 用 `asyncio.run` 收集 async generator 全部事件，断言事件序列与内容
- 技能接口用 `TestClient`（复用 `from main import app`），只读不改
- 明确不覆盖需要真实服务的分支（LLM / 9006 / 9007），保持离线可跑

## 关键断言

- SSE 格式：`event: X` / `data: {...}` / 尾部空行，JSON 中文不转义（ensure_ascii=False）
- approved_action 分支事件序列：`agent_thought` → `agent_message` → `message_end`
- agent_message.content 含"变更待人工执行"与"人工执行"；actions[0].type == "link"
- message_end 携带 conversation_id
