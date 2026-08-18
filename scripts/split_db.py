#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按表域机械拆分 app/db.py → app/db/ 包（纯内部重构，行为零变更）。

用法:
    python scripts/split_db.py

产出:
    app/db/__init__.py   统一 re-export 全部顶层符号（含私有辅助），保持外部导入兼容
    app/db/base.py       基础设施：连接/锁/通用查询/统计辅助
    app/db/schema.py     建表：init_session_db / init_config_db
    app/db/sessions.py   会话域
    app/db/seed.py       配置种子 + MCP 服务器/工具 CRUD
    app/db/employees.py  员工/技能域
    app/db/tasks.py      任务域
    app/db/kb.py         知识库域
    app/db/ops.py        运维监控域

依赖方向单向：base 无包内依赖，其余域仅依赖 base + 标准库 + seed_data + config。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app", "db.py")
OUT = os.path.join(ROOT, "app", "db")

STDLIB = {"json", "sqlite3", "threading", "uuid", "datetime"}

SEED_NAMES = [
    "MCP_SERVER_SEED", "MCP_TOOL_SEED", "MOCK_BG_TASKS", "MOCK_CONV_MESSAGES",
    "MOCK_EMPLOYEES", "MOCK_LONG_TASKS",
    "SKILL_DETAILS", "SKILLS",
]

# (模块名, 符号清单, 模块 docstring)
DOMAINS = [
    ("base", [
        "_db_lock", "_get_conn", "_ensure_column",
        "_query_rows", "_query_one", "_est_tokens", "_text_summary",
        "_agent_name_map", "_parse_route",
        "_COST_INPUT_PER_M", "_COST_OUTPUT_PER_M",
    ], "基础设施：SQLite 连接 / 全局锁 / 幂等补列 / 通用查询与统计辅助"),
    ("schema", [
        "init_session_db", "init_config_db",
    ], "建表：会话库 / 配置库初始化（init_*）"),
    ("sessions", [
        "ensure_conversation", "save_user_message", "save_agent_message",
        "list_conversations", "db_create_project", "db_list_projects",
        "db_rename_project", "db_delete_project", "db_update_conversation",
        "db_delete_conversation", "db_get_deleted_mock_convs",
        "db_mark_mock_conv_deleted", "db_share_conversation",
        "db_get_conversation_share", "db_get_conv_by_share",
        "get_conversation_messages", "_load_chat_history", "seed_mock_conversations",
    ], "会话域：对话 / 项目 / 分享 / 历史加载"),
    ("seed", [
        "seed_config_db", "sync_seed_employees", "ensure_mcp_server_mapping",
        "db_list_mcp_servers", "db_get_mcp_server", "db_upsert_mcp_server",
        "db_delete_mcp_server", "db_sync_server_tools", "db_list_mcp_tools",
        "db_get_mcp_tool", "db_update_mcp_tool",
    ], "配置种子 + MCP 服务器/工具 CRUD"),
    ("employees", [
        "db_list_employees", "db_get_employee", "db_upsert_employee",
        "db_delete_employee", "db_set_employee_skill_enabled",
        "db_link_employee_skills", "db_unlink_employee_skill",
        "db_list_skills", "db_get_skill", "db_set_skill_enabled",
        "db_upsert_skill", "db_delete_skill", "db_set_employee_enabled",
    ], "员工 / 技能域"),
    ("tasks", [
        "db_list_long_tasks", "db_get_long_task", "db_create_long_task",
        "db_update_long_task", "db_delete_long_task", "db_list_bg_tasks",
    ], "任务域：长任务 / 后台任务"),
    ("kb", [
        "db_list_knowledge_bases", "db_get_knowledge_base",
        "db_create_knowledge_base", "db_rename_knowledge_base",
        "db_delete_knowledge_base", "db_update_kb_stats", "db_add_kb_chunks",
        "db_clear_kb_chunks", "db_list_kb_chunks", "db_count_kb_chunks",
        "db_delete_kb_chunk", "db_get_kb_chunk", "db_bind_employee_kb",
        "db_get_employee_kb_ids", "db_get_employee_kb_names", "db_get_kb_employees",
    ], "知识库域：KB CRUD / 分块 / 员工绑定"),
    ("ops", [
        "OPS_ENTITY_TYPES", "init_ops_db", "db_get_setting", "db_set_setting",
        "db_get_settings_all", "ops_save_metric", "ops_save_metrics",
        "ops_get_metrics", "ops_get_latest_value", "ops_get_latest_snapshot",
        "ops_cleanup_old_metrics", "ops_save_logs", "ops_get_logs",
        "ops_count_logs", "ops_cleanup_old_logs", "ops_upsert_entity",
        "ops_save_entities", "ops_get_entities", "ops_get_entity",
        "ops_save_relations", "ops_get_relations",
    ], "运维监控域：设置 / 指标 / 日志 / 实体 / 关系"),
]


def collect_top_level(text):
    """返回 {name: (start_1based, end_1based)}，覆盖函数/类/顶层赋值常量。"""
    lines = text.splitlines()
    tree = ast.parse(text)
    entries = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            entries.append((node.name, node.lineno))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    entries.append((t.id, node.lineno))
    entries.sort(key=lambda x: x[1])
    total = len(lines)
    result = {}
    for i, (name, lineno) in enumerate(entries):
        end = entries[i + 1][1] - 1 if i + 1 < len(entries) else total
        result[name] = (lineno, end)
    return result


def extract_blocks(lines, spans):
    """按 (start, end) 行区间列表提取代码（lines 为 keepends 行），块间保留空行。"""
    parts = []
    for start, end in spans:
        block = lines[start - 1:end]
        # keepends 行直接拼接（行内已含 \n），避免二次 join 产生空行
        parts.append("".join(block).replace("\r", "").rstrip())
    return trim_tail_comments("\n\n\n".join(parts) + "\n")


def trim_tail_comments(code):
    """去掉代码块尾部的空行与注释行（旧文件分区标题等残留）。"""
    lines = code.splitlines()
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()
    if not lines:
        return code
    return "\n".join(lines) + "\n"


def collect_referenced_names(code):
    """收集代码块中所有引用的 Name 标识符集合。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        print(f"[WARN] 引用分析跳过（语法异常）：{e}")
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


def fmt_import(names, ordered):
    if not names:
        return None
    names = sorted(names, key=ordered.index) if ordered else sorted(names)
    if len(names) == 1:
        return f"from seed_data import {names[0]}"
    body = ",\n    ".join(names)
    return f"from seed_data import (\n    {body},\n)"


def render_module(module, doc, code, imports, all_names):
    """组装单个模块文件内容。"""
    lines = ["# -*- coding: utf-8 -*-", f'"""{doc}"""', ""]

    std = sorted(imports["stdlib"])
    for m in std:
        if m == "datetime":
            lines.append("from datetime import datetime")
        else:
            lines.append(f"import {m}")
    if std:
        lines.append("")

    seed = imports["seed"]
    if seed:
        lines.append(fmt_import(seed, SEED_NAMES))
        lines.append("")

    if "DB_PATH" in imports["dbpath"]:
        lines.append("from ..config import DB_PATH")
        lines.append("")

    base_imports = sorted(imports["base"])
    if base_imports:
        if len(base_imports) == 1:
            lines.append(f"from .base import {base_imports[0]}")
        else:
            lines.append("from .base import (\n    " + ",\n    ".join(base_imports) + ",\n)")
        lines.append("")

    cross = imports["cross"]  # {other_module: [names]}
    for other, names in sorted(cross.items()):
        names = sorted(names)
        if len(names) == 1:
            lines.append(f"from .{other} import {names[0]}")
        else:
            lines.append("from .{0} import (\n    {1},\n)".format(other, ",\n    ".join(names)))
        lines.append("")

    lines.append(code)
    return "\n".join(lines)


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines(keepends=True)
    top = collect_top_level(text)

    # 校验符号映射完整
    missing = []
    for mod, names, doc in DOMAINS:
        for n in names:
            if n not in top:
                missing.append(f"{mod}.{n}")
    if missing:
        print("[FATAL] 以下符号未在 db.py 顶层找到，中止：")
        for m in missing:
            print("  -", m)
        sys.exit(1)

    all_owner = {}
    for mod, names, doc in DOMAINS:
        for n in names:
            all_owner[n] = mod
    base_names = set(n for m, ns, d in DOMAINS if m == "base" for n in ns)

    os.makedirs(OUT, exist_ok=True)

    for mod, names, doc in DOMAINS:
        spans = sorted(top[n] for n in names)
        code = extract_blocks(lines, spans)
        referenced = collect_referenced_names(code)

        imports = {
            "stdlib": set(),
            "seed": set(),
            "base": set(),
            "dbpath": set(),
            "cross": {},
        }
        for name in referenced:
            if name in STDLIB:
                imports["stdlib"].add(name)
            elif name in SEED_NAMES:
                imports["seed"].add(name)
            elif name == "DB_PATH":
                imports["dbpath"].add(name)
            elif name in base_names and mod != "base":
                imports["base"].add(name)
            elif name in all_owner and all_owner[name] not in (mod, "base"):
                imports["cross"].setdefault(all_owner[name], set()).add(name)

        content = render_module(mod, doc, code, imports, all_owner)
        out_path = os.path.join(OUT, f"{mod}.py")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[生成] {out_path} ({len(code.splitlines())} 行代码)")

    # ── __init__.py：全量 re-export，保持顺序与原文件一致 ──
    init_lines = [
        "# -*- coding: utf-8 -*-",
        '"""SQLite 数据层包：按表域拆分后的统一出口。',
        "",
        "对外导入保持兼容：",
        "    from app import db            # db.init_session_db() 等",
        "    from . import db              # app 内部模块既有写法",
        "    from app.db import x          # 或 from .db import x",
        '"""',
        "",
    ]
    for mod, names, doc in DOMAINS:
        ordered = sorted(names, key=lambda n: top[n][0])
        if len(ordered) == 1:
            init_lines.append(f"from .{mod} import {ordered[0]}")
        else:
            init_lines.append(f"from .{mod} import (")
            for n in ordered:
                init_lines.append(f"    {n},")
            init_lines.append(")")
        init_lines.append("")
    with open(os.path.join(OUT, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(init_lines))
    print(f"[生成] {os.path.join(OUT, '__init__.py')}（re-export {sum(len(n) for _, n, _ in DOMAINS)} 个符号）")

    print("\n[完成] 请人工验证：python -c \"from app import db; from app.db import init_session_db, db_list_employees, _query_rows\"")
    print("确认无误后删除 app/db.py。")


if __name__ == "__main__":
    main()
