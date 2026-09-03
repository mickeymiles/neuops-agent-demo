#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 seed_data.py 中的最新定义幂等同步到已有数据库。

背景：seed.py 的增量同步**不覆盖** mcp_tools 的 name/desc（注释见 seed.py:152），
员工 prompt 受 emp_sync_seeded 一次性守卫保护。因此改了 seed_data.py 后，
已有库不会自动更新，需要本脚本把「权威定义」刷进去。

仅更新两类：
  1. mcp_tools 的 name / desc（按 id 精确匹配）
  2. employees 的 prompt（按 id 精确匹配）

用法: python3 sync_seed_defs.py [db_path]
"""
import json
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "neuops_sessions.db"

# 从源码读取权威定义
sys.path.insert(0, ".")
from seed_data import MOCK_EMPLOYEES, MCP_TOOL_SEED, SKILL_DETAILS  # noqa: E402

# 需要刷新的目标（白名单，避免误改其它记录）
TOOL_IDS = {"ontology_compute"}
EMP_IDS = {"emp-004"}
SKILL_IDS = {"skill-11", "skill-20"}

tools = {t["id"]: t for t in MCP_TOOL_SEED if t["id"] in TOOL_IDS}
emps = {e["id"]: e for e in MOCK_EMPLOYEES if e["id"] in EMP_IDS}

conn = sqlite3.connect(DB)
cur = conn.cursor()

print(f"目标库: {DB}")
print("=" * 64)

# ── 1. 工具定义 ──
for tid, t in tools.items():
    row = cur.execute(
        "SELECT name, desc FROM mcp_tools WHERE id=?", (tid,)).fetchone()
    if not row:
        print(f"  [跳过] 工具 {tid} 不存在于库")
        continue
    old_name, old_desc = row
    # 注意：params_schema 必须一并同步——LLM 看到的参数说明来自库里的这一列，
    # 不同步则源码里补的函数签名（参数名）不会生效，仍会以错误参数名调用。
    cur.execute("UPDATE mcp_tools SET name=?, desc=?, params_schema=? WHERE id=?",
                (t["name"], t["desc"],
                 json.dumps(t.get("params_schema", []), ensure_ascii=False), tid))
    print(f"  工具 {tid}")
    print(f"    name: {old_name}")
    print(f"       → {t['name']}")
    print(f"    desc: {(old_desc or '')[:60]}...")
    print(f"       → {t['desc'][:60]}...")

# ── 2. 员工 prompt ──
for eid, e in emps.items():
    row = cur.execute(
        "SELECT prompt FROM employees WHERE id=?", (eid,)).fetchone()
    if not row:
        print(f"  [跳过] 员工 {eid} 不存在于库")
        continue
    old_prompt = row[0] or ""
    new_prompt = e.get("prompt", "")
    cur.execute("UPDATE employees SET prompt=? WHERE id=?", (new_prompt, eid))
    print(f"  员工 {eid} prompt")
    print(f"    旧长度 {len(old_prompt)} 含'不自行重算': {'不自行重算' in old_prompt}")
    print(f"    新长度 {len(new_prompt)} 含'不自行重算': {'不自行重算' in new_prompt}")
    print(f"    新 prompt 提及 ontology_compute: {'ontology_compute' in new_prompt}")

# ── 3. Skill 的 prompt / flow ──
# 运行时 mode=skill 用的是 skills 表的 prompt（skill_loader 优先读库，
# 缺失才回落到 seed_data.py），所以改了源码必须同步到库才生效。
for sid in SKILL_IDS:
    det = SKILL_DETAILS.get(sid, {})
    if not det:
        continue
    row = cur.execute(
        "SELECT prompt, flow FROM skills WHERE id=?", (sid,)).fetchone()
    if not row:
        print(f"  [跳过] skill {sid} 不存在于库")
        continue
    old_prompt, old_flow = row
    new_prompt = det.get("prompt", old_prompt or "")
    new_flow = det.get("flow", old_flow or "")
    cur.execute("UPDATE skills SET prompt=?, flow=? WHERE id=?",
                (new_prompt, new_flow, sid))
    print(f"  skill {sid} prompt/flow")
    print(f"    prompt: {len(old_prompt or '')} → {len(new_prompt)} 字符"
          f"  | 去除了'不自行重算': "
          f"{'不自行重算' not in new_prompt and '不自行重算' in (old_prompt or '')}")
    print(f"    flow  : {len(old_flow or '')} → {len(new_flow)} 字符")

conn.commit()

# ── 校验 ──
print("=" * 64)
print("校验（回读）:")
for tid in tools:
    n, d = cur.execute(
        "SELECT name, desc FROM mcp_tools WHERE id=?", (tid,)).fetchone()
    ok = not any(k in (n + d) for k in ("临时口径", "非固化口径"))
    print(f"  {tid}: name={n!r}  无'临时口径'字样: {ok}")
for eid in emps:
    p = cur.execute(
        "SELECT prompt FROM employees WHERE id=?", (eid,)).fetchone()[0]
    print(f"  {eid}: 含 ontology_compute 指引: {'ontology_compute' in p}"
          f" | 仍含'不自行重算': {'不自行重算' in p}")

conn.close()
print("完成。请重启 9007 使进程重新加载。")
