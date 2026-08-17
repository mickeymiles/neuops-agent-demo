# -*- coding: utf-8 -*-
"""Agent 对话测试：SSE 事件格式 / 审批确认分支 / 技能中心接口
# 规格编号: NO-006 Agent 对话与 MCP（SSE 事件流/审批转人工/技能列表）
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agent_chat import mock_agent_run, sse_event  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def _collect(agen):
    """收集 async generator 的全部事件（已序列化 SSE 字符串）"""
    async def _run():
        return [ev async for ev in agen]
    return asyncio.run(_run())


def _parse_events(raw_events):
    """把 SSE 字符串列表解析为 [(event, data_dict), ...]"""
    parsed = []
    for raw in raw_events:
        event = None
        data = None
        for line in raw.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        parsed.append((event, data))
    return parsed


# ==================== sse_event 格式 ====================

def test_sse_event_format():
    """SSE 事件：event 行 / data JSON 行 / 尾部空行 / 中文不转义"""
    ev = sse_event("agent_message", {"content": "你好"})
    assert ev.startswith("event: agent_message\n")
    assert 'data: {"content": "你好"}\n\n' in ev
    assert ev.endswith("\n\n")


def test_sse_event_data_json_parseable():
    """data 部分必须是合法 JSON，且字段完整"""
    payload = {"content": "重启订单服务", "actions": [{"id": "a1", "type": "link"}]}
    ev = sse_event("agent_message", payload)
    data_line = [ln for ln in ev.splitlines() if ln.startswith("data: ")][0]
    parsed = json.loads(data_line[len("data: "):])
    assert parsed == payload


# ==================== mock_agent_run 审批确认分支（离线可跑） ====================

def _run_approved_action():
    return _parse_events(_collect(mock_agent_run(
        query="请重启订单服务", mode="free", selected_skill="",
        approved_action="重启订单服务",
    )))


def test_mock_agent_run_approved_action_sequence():
    """approved_action 非空：事件序列 agent_thought → agent_message → message_end"""
    events = _run_approved_action()
    assert [e[0] for e in events] == ["agent_thought", "agent_message", "message_end"]


def test_mock_agent_run_approved_action_thought():
    """agent_thought：确认文案包含操作名与人工执行提示"""
    events = _run_approved_action()
    thought = events[0][1]
    assert "重启订单服务" in thought
    assert "人工确认意愿" in thought


def test_mock_agent_run_approved_action_message():
    """agent_message：content 含变更待人工执行说明，actions 提供人工执行入口"""
    events = _run_approved_action()
    msg = events[1][1]
    assert "变更待人工执行" in msg["content"]
    assert "人工执行" in msg["content"]
    assert msg["actions"] and msg["actions"][0]["type"] == "link"
    assert msg["actions"][0]["url"].startswith("http")


def test_mock_agent_run_approved_action_end():
    """message_end：携带会话标识，且为最后一个事件"""
    events = _run_approved_action()
    end = events[-1][1]
    assert "conversation_id" in end


# ==================== 技能中心接口 ====================

def test_skills_api():
    """GET /api/skills：返回技能列表，字段含 id/name/desc/category/enabled"""
    r = client.get("/api/skills")
    assert r.status_code == 200
    skills = r.json()["skills"]
    assert isinstance(skills, list) and len(skills) > 0
    for s in skills:
        assert s["id"] and s["name"]
        assert "desc" in s and "category" in s and "enabled" in s


def test_skills_full_api():
    """GET /api/skills/full：与 /api/skills 结构一致"""
    r = client.get("/api/skills/full")
    assert r.status_code == 200
    skills = r.json()["skills"]
    assert isinstance(skills, list) and len(skills) > 0
    assert all(s["id"] and s["name"] for s in skills)
