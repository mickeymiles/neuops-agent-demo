# -*- coding: utf-8 -*-
"""DSH 内核引擎：DeepSeek Harness 子进程执行 + SSE 事件映射

架构：
  FastAPI /api/chat --engine=dsh--> dsh_agent_run()
      └─ asyncio subprocess ──> dsh --profile headless "<task>"
           ├─ stdout : 最终 assistant 文本（headless 等待任务停稳后整体输出）
           ├─ stderr : 失败时的错误信息
           └─ 退出码 : 0 成功 / 1 失败

事件协议与 legacy 引擎（agent_chat.mock_agent_run）完全一致，前端零改动：
  agent_thought : 运行状态文本
  tool_call     : {"tool": ..., "command": ...}（P2 工具桥透传）
  tool_result   : {"tool": ..., "summary": ...}（P2 工具桥透传）
  agent_message : {"content": <markdown>, "actions": []}
  message_end   : {"conversation_id": <conv_id>}

说明：headless 为「提交单任务 → 跑完 → 输出最终文本」模式，本引擎在任务执行
期间以 agent_thought 汇报状态；任务完成后读取 headless 会话事件（zstd JSONL），
将工具调用（tool_call/tool_result）透传给前端，最后输出最终文本 agent_message。
工具桥为 dsh/neuops_tool_cli.py（CLI 封装 9007 配置化工具，DSH 经内置 Bash 工具调用）。
"""
import asyncio
import glob
import json
import os
import re
import shutil

from .config import DSH_BIN, DSH_HOME, DSH_MAX_HISTORY, DSH_PROFILE, DSH_TIMEOUT

try:  # zstandard 用于解压 headless session 事件（可选，未装则跳过事件透传）
    import zstandard as zstd
except ImportError:
    zstd = None


def _sse(event: str, data) -> str:
    """构造 SSE 事件块（与 app/agent_chat.py 的 sse_event 完全同格式）"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_dsh_bin() -> str:
    """解析 dsh CLI 路径：env DSH_BIN > PATH which dsh > npx 缓存兜底"""
    if DSH_BIN:
        return DSH_BIN
    p = shutil.which("dsh")
    if p:
        return p
    # macOS/Linux npx 全局缓存兜底
    hits = sorted(
        glob.glob(os.path.expanduser("~/.npm/_npx/*/node_modules/.bin/dsh")),
        reverse=True,
    )
    return hits[0] if hits else ""


def _profile_dir() -> str:
    """DSH profile 目录（cwd 与 bundle 解析上下文）"""
    return os.path.join(DSH_HOME, "profiles", DSH_PROFILE)


def _tool_cli_path() -> str:
    """工具桥 CLI 的绝对路径（项目根/dsh/neuops_tool_cli.py），本机/服务器通用"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dsh",
        "neuops_tool_cli.py",
    )


def _build_task(query: str, history: list, mode: str = "free", selected_skill: str = "") -> str:
    """把角色提示 + 工具说明 + 会话历史 + 当前问题拼成 headless 单任务文本

    P3：mode=skill 时注入数字员工角色（emp-005/001 等技能型员工走 DSH 子代理化）
    """
    parts = []
    if mode == "skill" and selected_skill:
        parts.append(
            f"你的身份：NeuOps 工作台的数字员工，当前技能为【{selected_skill}】。"
            "请以该专家的视角回答业务问题。"
        )
    parts.append(
        "业务数据查询说明：如需查询业务数据（合同/指标/表），使用 Bash 工具执行命令"
        f" `python3 {_tool_cli_path()} --help-tools` 查看可用工具，然后按示例调用；"
        "调用失败时先运行 --help-tools 确认工具与参数。"
    )
    if history:
        for h in (history or [])[-DSH_MAX_HISTORY:]:
            role = h.get("role", "")
            content = str(h.get("content", "")).strip()
            if role == "user" and content:
                parts.append(f"用户: {content}")
            elif role == "assistant" and content:
                parts.append(f"助手: {content}")
    parts.append(f"用户(当前问题): {query}")
    return "\n".join(parts)


def _sessions_root() -> str:
    """DSH session 持久化根目录（headless 会话事件所在）"""
    return os.path.join(DSH_HOME, "sessions")


def _snapshot_sessions() -> dict:
    """运行前快照：{ (profile_dir, session_dir): mtime }"""
    root = _sessions_root()
    snap = {}
    if not os.path.isdir(root):
        return snap
    for profile_dir in os.listdir(root):
        pd = os.path.join(root, profile_dir)
        if not os.path.isdir(pd):
            continue
        for s in os.listdir(pd):
            if s.startswith("session-"):
                sp = os.path.join(pd, s)
                try:
                    snap[(profile_dir, s)] = os.path.getmtime(sp)
                except OSError:
                    pass
    return snap


def _find_new_session_dir(before: dict):
    """运行后找最新 session 目录（新增或更新的），返回绝对路径或 None"""
    root = _sessions_root()
    if not os.path.isdir(root):
        return None
    candidates = []
    for profile_dir in os.listdir(root):
        pd = os.path.join(root, profile_dir)
        if not os.path.isdir(pd):
            continue
        for s in os.listdir(pd):
            if not s.startswith("session-"):
                continue
            sp = os.path.join(pd, s)
            try:
                mtime = os.path.getmtime(sp)
            except OSError:
                continue
            if (profile_dir, s) not in before or mtime > before[(profile_dir, s)]:
                candidates.append((mtime, sp))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _read_tool_events(session_dir: str) -> list:
    """读取 headless session 事件文件（zstd JSONL），映射为业务工具事件

    返回 [{"kind": "tool_call" | "tool_result", "data": {...}}, ...]
    """
    if zstd is None:
        return []
    path = os.path.join(session_dir, "session.jsonl.zstd")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            with zstd.ZstdDecompressor().stream_reader(fh) as r:
                data = r.read()
    except Exception:
        return []
    events = []
    call_names = {}  # callId -> 工具显示名（tool_result 按 callId 关联同名）
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        d = e.get("data") or {}
        if t == "tool/call":
            name = d.get("name", "tool")
            call_id = d.get("callId", "")
            args = {}
            try:
                args = json.loads(d.get("arguments") or "{}")
            except Exception:
                pass
            command = str(args.get("command", ""))
            m = re.search(r"neuops_tool_cli\.py\s+(\S+)", command)
            tool_id = m.group(1) if m else ""
            display = f"tool_bridge.{tool_id}" if tool_id else name
            if call_id:
                call_names[call_id] = display
            events.append({
                "kind": "tool_call",
                "data": {"tool": display, "command": command[:300], "callId": call_id},
            })
        elif t == "tool/result":
            msg = d.get("message") or {}
            source = msg.get("source") or {}
            call_id = source.get("callId", "")
            content = msg.get("content") or []
            text = ""
            is_err = False
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("isError"):
                    is_err = True
                for cc in (c.get("content") or []):
                    if isinstance(cc, dict) and cc.get("type") == "text":
                        text += cc.get("text", "")
            events.append({
                "kind": "tool_result",
                "data": {
                    "tool": call_names.get(call_id, "tool_bridge"),
                    "summary": f"{'[错误] ' if is_err else ''}{text.strip()[:400]}",
                    "callId": call_id,
                },
            })
    return events


async def dsh_agent_run(
    query: str,
    history: list = None,
    conversation_id: str = None,
    mode: str = "free",
    selected_skill: str = "",
):
    """DSH 引擎执行，产出与 legacy 一致的 SSE 事件流（async generator）"""
    conv_id = conversation_id or ""
    dsh_session_id = ""
    yield _sse("agent_thought", "🧠 已切换 DSH 内核引擎（DeepSeek Harness），正在初始化...")

    dsh_bin = _resolve_dsh_bin()
    if not dsh_bin:
        yield _sse("agent_message", {
            "content": "## ⚠️ DSH 引擎不可用\n\n未找到 `dsh` CLI。请安装 DeepSeek Harness 或设置环境变量 `DSH_BIN` 指向 dsh 可执行文件后重试。",
            "actions": [],
        })
        yield _sse("message_end", {"conversation_id": conv_id, "dsh_session_id": ""})
        return

    task = _build_task(query, history, mode=mode, selected_skill=selected_skill)
    cmd = [dsh_bin, "--profile", DSH_PROFILE, task]
    yield _sse("agent_thought", f"⚙️ 正在调用 DSH runtime（profile={DSH_PROFILE}）执行任务，请稍候...")

    sessions_before = _snapshot_sessions()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_profile_dir(),
        )
    except FileNotFoundError as e:
        yield _sse("agent_message", {
            "content": f"## ⚠️ DSH 启动失败\n\n```\n{e}\n```",
            "actions": [],
        })
        yield _sse("message_end", {"conversation_id": conv_id, "dsh_session_id": ""})
        return

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=DSH_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        yield _sse("agent_message", {
            "content": f"## ⚠️ DSH 任务超时（>{DSH_TIMEOUT}s）\n\n任务仍在执行，请重试或调大 `DSH_TIMEOUT`。",
            "actions": [],
        })
        yield _sse("message_end", {"conversation_id": conv_id, "dsh_session_id": ""})
        return

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0 or not stdout:
        err = stderr or f"exit code {proc.returncode}"
        yield _sse("agent_message", {
            "content": f"## ⚠️ DSH 任务失败\n\n```\n{err[:2000]}\n```",
            "actions": [],
        })
    else:
        # 工具事件透传（P2 工具桥）：从本次 headless session 事件读取 tool_call/tool_result
        new_session = _find_new_session_dir(sessions_before)
        if new_session:
            dsh_session_id = os.path.basename(new_session)
            if dsh_session_id.startswith("session-"):
                dsh_session_id = dsh_session_id[len("session-"):]
            for ev in _read_tool_events(new_session):
                if ev["kind"] == "tool_call":
                    yield _sse("tool_call", ev["data"])
                elif ev["kind"] == "tool_result":
                    yield _sse("tool_result", ev["data"])
        yield _sse("agent_message", {"content": stdout, "actions": []})
    yield _sse("message_end", {"conversation_id": conv_id, "dsh_session_id": dsh_session_id})
