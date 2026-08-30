# -*- coding: utf-8 -*-
"""LLM 提议器 + 规则约束闭环（KNO-R-02）：LLM 选动作 → 规则校验 → 拒绝则带原因重选 → 兜底规则式。
LLM 只做选择与编排；计算/持久化/邮件网关不交给 LLM（DET-R-01）。
复用现轨 DeepSeek 调用链只读；实现独立于现轨。
"""
import json
import os

from . import actions as act, knowledge


def _ask_llm_action(allowed: list, ctx: dict, rejections: list):
    """调用 DeepSeek 让其在 allowed 动作中选一个，返回 {action, reason}。失败返回 None。"""
    try:
        from app.agent_chat import _load_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    except Exception:
        return None
    key = _load_deepseek_key()
    if not key:
        return None
    import httpx
    sys_prompt = (
        "你是本体化备件询价智能体 emp-009 的决策核心。当前只有确定性的动作集合可以选，"
        "只输出 JSON：{\"action\": \"<动作id>\", \"reason\": \"一句话理由\"}，不要多余文字/代码块标记。\n"
        "可行动作：\n" + json.dumps(allowed, ensure_ascii=False) +
        "\n动作语义：" + json.dumps(act.ACTION_REGISTRY, ensure_ascii=False) +
        "\n领域规则摘要：" + json.dumps([{ "id": r["id"], "target": r["target"], "desc": r["desc"]} for r in knowledge.RULES], ensure_ascii=False) +
        "\n选择原则：只选前置条件当前已满足、且能推进当前状态的动作；拿不准就选最保守的维持动作。"
    )
    user_msg = ("当前任务事实(JSON)：\n" + json.dumps(ctx, ensure_ascii=False, default=str))
    if rejections:
        user_msg += ("\n\n系统已拒绝以下动作并给出原因，请换一个合法动作：\n" + json.dumps(rejections, ensure_ascii=False))
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_msg},
    ]
    try:
        r = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.1}, timeout=40,
        )
        content = r.json()["choices"][0]["message"]["content"]
        start, end = content.find("{"), content.rfind("}")
        obj = json.loads(content[start:end + 1])
        action = str(obj.get("action") or "").strip()
        if action in act.list_action_ids():
            return {"action": action, "reason": str(obj.get("reason") or "").strip()}
    except Exception:
        pass
    return None


def llm_decide_action(ctx: dict, max_tries: int = 3):
    """LLM 提议 + 规则校验闭环。返回 (action, reason, via_llm)。
    每轮：LLM 给动作 → knowledge.check_target 校验前置；不满足则记录拒绝原因并重问。
    达上限或 LLM 不可用 → 回退规则式提议器。
    """
    use_llm = os.getenv("ONT_USE_LLM", "0") == "1"
    if not use_llm:
        from .decision import propose_action
        aid, ex, inn, reason = propose_action(ctx)
        return aid, reason or "", False

    allowed = act.list_action_ids()
    rejections = []
    for _ in range(max_tries):
        cand = _ask_llm_action(allowed, ctx, rejections)
        if not cand:
            break
        ok, failed = knowledge.check_target(cand["action"], ctx)
        if ok:
            return cand["action"], cand["reason"], True
        rejections.append({"action": cand["action"], "rejected": failed})
    from .decision import propose_action
    aid, ex, inn, reason = propose_action(ctx)
    return aid, reason or "LLM未收敛，回退规则式", False