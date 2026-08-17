# 任务清单：NO-006 Agent 对话与 MCP 测试

- [x] T1 确认 sse_event / mock_agent_run（approved_action 分支）/ 技能路由真实行为
- [x] T2 编写 `tests/test_agent_chat.py`
  - [x] T2.1 用例 1：sse_event 格式（event/data/空行/中文不转义）
  - [x] T2.2 用例 2：mock_agent_run approved_action 事件序列与内容
  - [x] T2.3 用例 3：GET /api/skills 字段结构
  - [x] T2.4 用例 4：GET /api/skills/full 字段结构
- [x] T3 运行 `python3 -m pytest tests/test_agent_chat.py -q` 通过（离线）
- [x] T4 回归 neuops 既有测试不受影响
- [x] T5 归档 `changes/20260817-no006-agent-chat-tests` → `archive/`
- [x] T6 更新 `specs/TRACEABILITY.md`（NO-006 覆盖状态）与 `archive/README.md`
