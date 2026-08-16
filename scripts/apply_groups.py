#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按描述为技能 / MCP 工具打初步业务分组（幂等，可重复执行）。
分组口径（与工具描述一致）：
  运维 —— 监控告警、日志、拓扑、变更、工单、数据库、容器、安全
  经营 —— 9006 合同比对 / ETL 指标 / 原子明细查询
  研发 —— 9006 代码读取与修改
用法：
  python3 scripts/apply_groups.py [DB_PATH]   # 默认项目根 neuops_sessions.db
"""
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "neuops_sessions.db")

# ── 技能分组（按 id） ──────────────────────────────
SKILL_GROUPS = {
    "运维": [
        "skill-1", "skill-2", "skill-3", "skill-4", "skill-5",
        "skill-6", "skill-7", "skill-8", "skill-9",
    ],
    "经营": ["skill-10", "skill-11", "skill-12"],
    "研发": ["skill-13"],
}

# ── MCP 工具分组（按 id） ──────────────────────────
TOOL_GROUPS = {
    "运维": [
        "get_business_metric", "search_service_log", "query_cmdb_topology",
        "query_change_record", "query_alarm_info", "run_auto_job",
        "query_change_risk", "verify_service_status", "search_slow_query",
        "query_container_resource", "scan_vulnerability",
    ],
    "经营": [
        "query_contracts", "get_comparison_results", "get_contract_stats",
        "export_report", "get_etl_metrics", "query_ontology",
        "list_tables", "get_table_schema", "query_table", "get_metrics",
    ],
    "研发": [
        "list_project_files", "read_code_file", "edit_code_file",
        "search_code", "write_new_file", "run_shell",
    ],
}


def apply_group(conn, table: str, gid: str, group_map: dict) -> int:
    n = 0
    for group, ids in group_map.items():
        for i in ids:
            cur = conn.execute(
                f"UPDATE {table} SET `group`=? WHERE id=?", (group, i))
            if cur.rowcount:
                n += cur.rowcount
            else:
                print(f"  ⚠ {table} 未命中: {i} ({group})")
    return n


def print_stats(conn):
    for table in ("skills", "mcp_tools", "mcp_servers"):
        rows = conn.execute(
            f"SELECT `group`, COUNT(*) FROM {table} GROUP BY `group`").fetchall()
        print(f"  {table}: {dict(rows)}")


def main():
    print(f"分组脚本 → {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        n_skill = apply_group(conn, "skills", "skill_id", SKILL_GROUPS)
        n_tool = apply_group(conn, "mcp_tools", "tool_id", TOOL_GROUPS)
        conn.commit()
        print(f"✅ 技能分组更新 {n_skill} 条，MCP 工具分组更新 {n_tool} 条")
        print_stats(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
