#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径2验证：智能体问答能否正确调用本体工具并作答。

向 9007 的 /api/chat 发一个需要本体计算的问题，解析 SSE 流，
观察：是否触发 tool_call(ontology_compute) → 工具返回值 → 最终回答是否正确。

用法: python3 verify_agent_qa.py [base_url]
"""
import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9006"
SKILL = sys.argv[2] if len(sys.argv) > 2 else "skill-11"

# 合同额100万、成本80万 → ROI = (100-80)/80 = 0.25
QUERY = "某项目合同额100万元，已发生成本80万元，请计算该项目的ROI（投资回报率）。"
EXPECT_ROI = 0.25


def parse_sse(raw: str):
    """从 SSE 文本中抽取事件"""
    events = []
    for block in raw.split("\n\n"):
        evt, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                evt = line[6:].strip()
            elif line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                except Exception:
                    data = line[5:].strip()
        if evt:
            events.append((evt, data))
    return events


def main():
    print(f"目标: {BASE}   skill: {SKILL}")
    print(f"提问: {QUERY}")
    print("-" * 70)

    try:
        with httpx.stream("POST", f"{BASE}/api/chat",
                          json={"query": QUERY, "mode": "skill",
                                "selected_skill": SKILL},
                          timeout=180, trust_env=False) as r:
            raw = "".join(chunk for chunk in r.iter_text())
    except Exception as e:
        print(f"请求失败: {e}")
        return 1

    events = parse_sse(raw)
    if not events:
        print("未解析到 SSE 事件，原始响应前 500 字符：")
        print(raw[:500])
        return 1

    tool_calls, tool_results, thoughts, answer = [], [], [], ""
    route = None
    for evt, data in events:
        if evt == "tool_call" and isinstance(data, dict):
            tool_calls.append(data)
        elif evt == "tool_result" and isinstance(data, dict):
            tool_results.append(data)
        elif evt == "agent_thought":
            thoughts.append(data if isinstance(data, str) else str(data))
        elif evt == "agent_message" and isinstance(data, dict):
            answer = data.get("content", "")
        elif evt == "route" and isinstance(data, dict):
            route = data

    print(f"路由: {route}")
    print(f"思考: {len(thoughts)} 段")
    for t in thoughts[:3]:
        print(f"   · {str(t)[:110]}")

    print(f"\n工具调用 {len(tool_calls)} 次:")
    for tc in tool_calls:
        print(f"   → {tc.get('tool')}  args={json.dumps(tc.get('args') or tc.get('params') or {}, ensure_ascii=False)[:150]}")

    print(f"\n工具返回 {len(tool_results)} 次:")
    hit_roi = False
    for tr in tool_results:
        s = json.dumps(tr, ensure_ascii=False)
        print(f"   ← {tr.get('tool')}: {s[:230]}")
        if str(EXPECT_ROI) in s or "0.25" in s:
            hit_roi = True

    print(f"\n最终回答:\n{answer[:500]}")
    print("-" * 70)

    used_ontos = any("ontology_compute" in json.dumps(tc, ensure_ascii=False)
                     for tc in tool_calls)
    roi_in_answer = ("0.25" in answer) or ("25%" in answer)

    print(f"是否调用 ontology_compute : {'是' if used_ontos else '否'}")
    print(f"工具返回含 roi=0.25       : {'是' if hit_roi else '否'}")
    print(f"最终回答含 0.25/25%       : {'是' if roi_in_answer else '否'}")

    # 注：SSE 的 tool_result 是摘要(_tool_result_summary)，不含完整 result，
    # 因此不能凭它判定数字真伪。给 LLM 的完整结果在 messages 里（见 agent_chat L191）。
    # 这里改为：调用了本体工具 + 未出现 param_error + 回答正确 = 通过。
    param_error = any('param_error' in json.dumps(x, ensure_ascii=False)
                      for x in tool_calls + tool_results)
    print(f"工具调用未报 param_error : {'是' if not param_error else '否'}")
    ok = used_ontos and (not param_error) and roi_in_answer
    print("-" * 70)
    print("路径2 结论:", "通畅 —— 智能体正确调用本体工具并给出正确答案" if ok else "存在问题，见上")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
