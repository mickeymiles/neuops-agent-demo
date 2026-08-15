# -*- coding: utf-8 -*-
"""main.py → app/ 模块化拆分脚本（仅切分内容，import 头/装饰器修正由后续步骤完成）
行号以 main.py 1-based 为准。
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "main.py")

lines = open(SRC, encoding="utf-8").read().split("\n")


def extract(segments):
    """segments: list of (start, end) 1-based inclusive → 拼接内容"""
    parts = []
    for s, e in segments:
        parts.append("\n".join(lines[s - 1:e]))
    return "\n\n".join(parts)


# 目标文件 → 行号区间（1-based, inclusive）
PLAN = {
    "app/mock_data.py": [(37, 113)],
    "app/mcp_tools.py": [(119, 192)],
    # agent_chat: mock_agent_run + SSE/DeepSeek/BIZ/execute_biz_tool + /api/chat 路由
    "app/agent_chat.py": [(195, 880), (882, 1108), (1451, 1515)],
    "app/devtools.py": [(1110, 1450)],
    # workspace: conversations/skills/todos/bg-tasks/knowledge + conv messages + skills full
    "app/routes_workspace.py": [(1517, 1621), (2668, 2683), (2690, 2698)],
    "app/routes_employees.py": [(1800, 1884)],
    "app/routes_tasks.py": [(1886, 2020)],
    "app/traditional_pages.py": [(1622, 1630), (1637, 1794)],
    # db: 连接/建表/种子/db_* 系列 + _query_rows 等辅助（2025 DB_PATH 起）
    "app/db.py": [(2025, 2666), (2705, 2750)],
    "app/alert_engine.py": [(2757, 2877)],
    "app/routes_monitor.py": [(2880, 3267)],
}

for rel, segs in PLAN.items():
    content = extract(segs)
    path = os.path.join(BASE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content + "\n")
    print(f"{rel}: {len(content.splitlines())} lines")

print("DONE")
