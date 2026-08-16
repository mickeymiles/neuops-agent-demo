#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DSH 工具桥：把 9007 工作台的配置化工具协议封装为 CLI，供 DSH 内置 Bash 工具调用。

DSH 侧无需任何插件开发：DSH 的 dsh-tool-bash 以 Bash 工具方式执行本 CLI，
工具发现用 `--list-tools`，执行结果以 JSON 输出到 stdout。

用法：
  python3 dsh/neuops_tool_cli.py --list-tools                 # 列出员工绑定的可用工具
  python3 dsh/neuops_tool_cli.py <tool_id> --arg value ...    # 调用工具（arg 即工具参数名）
  python3 dsh/neuops_tool_cli.py query_table --table_name 总合同表 --limit 50

退出码：0 成功（stdout 为工具结果 JSON）；1 失败（stdout 为 {"error": ...}）。

实现说明：复用 9007 的 execute_configured_tool（按 mcp_tools 表配置动态调用
MCP Server），与 legacy 引擎完全同源，保证工具行为一致。
"""
import argparse
import asyncio
import json
import os
import sys

# 允许从任意 cwd 运行（服务器 /home/ubuntu/neuops-agent-demo 或本机仓库根）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent_chat import build_employee_tools, execute_configured_tool  # noqa: E402


def _parse_kwargs(argv):
    """解析 --key value 形式的参数为 dict（忽略非 -- 前缀的杂项）"""
    args = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                args[key] = argv[i + 1]
                i += 2
            else:
                args[key] = True
                i += 1
        else:
            i += 1
    return args


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="neuops_tool_cli.py",
        description="NeuOps 工具桥 CLI：DSH Bash 工具调用 9007 配置化工具的入口",
    )
    parser.add_argument("tool_id", nargs="?", help="工具 ID，如 query_table / get_metrics")
    parser.add_argument("--list-tools", action="store_true", help="列出员工绑定的可用工具（JSON）")
    parser.add_argument("--employee", default="emp-004", help="员工 ID（默认 emp-004 经营业务专家）")
    parser.add_argument("--help-tools", action="store_true", help="输出工具清单的纯文本说明（适合喂给 DSH 系统提示）")
    args, rest = parser.parse_known_args()

    if args.list_tools or args.help_tools:
        tools = build_employee_tools(args.employee)
        if args.help_tools:
            lines = [f"可用工具（员工 {args.employee}）："]
            for t in tools:
                fn = t["function"]
                params = fn.get("parameters", {}).get("properties", {})
                req = fn.get("parameters", {}).get("required", [])
                arg_desc = "，".join(
                    f"{n}({'必填' if n in req else '可选'}: {p.get('description', '')})"
                    for n, p in params.items()
                )
                lines.append(f"- {fn['name']}: {fn.get('description', '')} 参数[{arg_desc}]")
                lines.append(f"  调用示例: python3 dsh/neuops_tool_cli.py {fn['name']} <--参数名 值 ...>")
            print("\n".join(lines))
            return 0
        out = {
            "employee": args.employee,
            "tools": [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "parameters": t["function"]["parameters"],
                }
                for t in tools
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if not args.tool_id:
        print(json.dumps(
            {"error": "缺少工具 ID。先运行 --list-tools 查看可用工具（--help-tools 查看纯文本说明）。"},
            ensure_ascii=False,
        ))
        return 1

    kwargs = _parse_kwargs(rest)
    try:
        result = asyncio.run(execute_configured_tool(args.tool_id, kwargs))
    except Exception as e:  # noqa: BLE001
        result = {"error": f"工具桥执行异常: {e}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
