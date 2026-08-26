# -*- coding: utf-8 -*-
"""
Skill 加载器（V2 规范版）

设计原则：
  Skill 定义存储在 skills/*.json 文件中（按需读取，支持热更新）
  同时保留 seed_data.py 的 SKILL_DETAILS 作为兼容层（旧 Skill 仍从 seed_data.py 读）
  读取优先级：JSON 文件 > seed_data.py

缓存策略：基于 mtime 的文件缓存，文件变更时自动重新加载
"""

import json
import os
import time
from typing import Optional, Dict, Any, List

# ── 路径配置 ──
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
_SEED_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed_data.py")

# 确保 skills 目录存在
os.makedirs(_SKILLS_DIR, exist_ok=True)

# ── 缓存：skill_id → {prompt: str, skill: dict, mtime: float, tools: list} ──
_cache: Dict[str, Dict[str, Any]] = {}


def _get_json_path(skill_id: str) -> str:
    return os.path.join(_SKILLS_DIR, f"{skill_id}.json")


def _build_prompt_from_skill(sk: dict) -> str:
    """把结构化 Skill 定义转译为 LLM 可读的 system prompt 文本。"""
    lines = []
    meta = sk

    # ── 头部：Skill 元信息 ──
    lines.append(f"# Skill: {meta['name']} ({meta['skill_id']})")
    lines.append(f"版本: {meta['version']}")
    lines.append(f"触发意图: {meta['trigger_intent']}")
    lines.append(f"退出条件: {meta['exit_condition']}")
    lines.append("")

    # ── 字段模型 ──
    lines.append("## 字段模型（会话侧校验）")
    lines.append("")
    fm = meta.get("field_model", {})

    lines.append("### 必填字段（必须采集）")
    for fname, fdef in fm.items():
        if fdef.get("required") in ("must",):
            lines.append(f"- **{fname}** ({fdef.get('label', fname)}): {fdef.get('type')}, 约束: {fdef.get('constraint', '')}")
    lines.append("")

    lines.append("### 条件触发字段")
    for fname, fdef in fm.items():
        if fdef.get("required") == "conditional":
            lines.append(f"- **{fname}** ({fdef.get('label', fname)}): 当 {fdef.get('condition', '')} 时采集")
    lines.append("")

    lines.append("### 选填字段（不问用户）")
    for fname, fdef in fm.items():
        if fdef.get("required") == "optional":
            lines.append(f"- **{fname}** ({fdef.get('label', fname)}): {fdef.get('description', '')}")
    lines.append("")

    # ── 状态机 ──
    lines.append("## 状态机（严格按此流转）")
    lines.append("")
    lines.append("### 状态流转表")
    lines.append("| 状态 | 动作 | 流转条件 | 下一状态 |")
    lines.append("|------|------|---------|---------|")
    for st in meta.get("state_machine", []):
        state = st["state"]
        action = st.get("action", "")
        if "transitions" in st:
            for tr in st["transitions"]:
                cond = tr["condition"]
                nxt = tr["next"]
                lines.append(f"| {state} | {action} | {cond} | {nxt} |")
        else:
            nxt = st.get("next", "")
            lines.append(f"| {state} | {action} | - | {nxt} |")
    lines.append("")

    # ── 话术模板 ──
    lines.append("## 话术模板（必须原样使用，变量用 {xxx} 占位）")
    lines.append("")
    for tname, tpl in meta.get("dialog_templates", {}).items():
        lines.append(f"### {tname}")
        lines.append(str(tpl))
        lines.append("")

    # ── 函数绑定 ──
    fb = meta.get("function_binding", {})
    if fb:
        lines.append("## 函数绑定（Skill 只声明，不实现）")
        lines.append("")
        lines.append(f"- 绑定函数: **{fb['function_id']}**")
        lines.append(f"- 传递数据: {fb['pass_data']}")
        if fb.get("note"):
            lines.append(f"- 注意: {fb['note']}")
        lines.append("")

    # ── 红线 ──
    lines.append("## 红线（违反即出错）")
    lines.append("")
    lines.append("- ❌ 一次性列出多个缺失项追问 → 必须分轮，每次只问1项")
    lines.append("- ❌ 追问用户选择供应商 → 默认带全量资源池，不问")
    lines.append("- ❌ 追问 project_id / project_name → 绝对禁止，Tool 层处理")
    lines.append("- ❌ 用自然语言自由发挥追问 → 必须用话术模板")
    lines.append("- ❌ 编造字段值 → 取不到就问，不猜")
    lines.append("- ❌ 在 Skill 中实现 HTTP/DB/SMTP 调用 → 全部下沉 Tool 层")
    lines.append("- ❌ 解析原始 HTTP 错误码 → Tool 层已封装为 {success, msg, data}")
    lines.append("")

    # ── 查询工具调用规则 ──
    tools_section = meta.get("tools_section", "")
    if tools_section:
        lines.append("## 查询工具调用（Skill 声明调用，Tool 层实现）")
        lines.append("")
        lines.append(tools_section)
        lines.append("")

    return "\n".join(lines)


def load_skill(skill_id: str) -> Optional[Dict[str, Any]]:
    """加载 Skill 定义，支持热更新。

    返回结构：
    {
        "prompt": str,         # LLM system prompt
        "skill": dict,         # 原始结构化定义
        "tools": list,         # 关联工具列表
        "source": "json"|"seed_data",  # 数据来源
        "mtime": float         # 文件修改时间
    }

    优先级：JSON 文件 > seed_data.py
    """
    json_path = _get_json_path(skill_id)

    # ── 优先从 JSON 文件加载 ──
    if os.path.isfile(json_path):
        mtime = os.path.getmtime(json_path)
        cached = _cache.get(skill_id)
        if cached and cached["mtime"] == mtime:
            return cached

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                sk = json.load(f)
            prompt = _build_prompt_from_skill(sk)
            result = {
                "prompt": prompt,
                "skill": sk,
                "tools": sk.get("tools", []),
                "source": "json",
                "mtime": mtime,
            }
            _cache[skill_id] = result
            return result
        except Exception as e:
            print(f"[skill_loader] 加载 JSON Skill 失败 {skill_id}: {e}")
            # 降级到 seed_data

    # ── 降级：从 seed_data.py 加载（旧版 Skill） ──
    return _load_from_seed_data(skill_id)


def _load_from_seed_data(skill_id: str) -> Optional[Dict[str, Any]]:
    """从 seed_data.py 的 SKILL_DETAILS 加载（兼容旧 Skill）。"""
    try:
        import sys
        if os.path.dirname(_SEED_DATA_PATH) not in sys.path:
            sys.path.insert(0, os.path.dirname(_SEED_DATA_PATH))
        import importlib
        import seed_data
        importlib.reload(seed_data)  # 强制重新加载
        sd = seed_data.SKILL_DETAILS
    except Exception as e:
        print(f"[skill_loader] 加载 seed_data 失败: {e}")
        # 最终兜底：硬编码一些 Skill
        return _get_fallback_skill(skill_id)

    skill_def = sd.get(skill_id)
    if not skill_def:
        return None

    # 检查是否是结构化 Skill（有 field_model）
    if skill_def.get("field_model"):
        prompt = _build_prompt_from_skill(skill_def)
    else:
        prompt = skill_def.get("prompt", "")

    return {
        "prompt": prompt,
        "skill": skill_def,
        "tools": skill_def.get("tools", []),
        "source": "seed_data",
        "mtime": time.time(),
    }


def _get_fallback_skill(skill_id: str) -> Optional[Dict[str, Any]]:
    """最终兜底：返回一个最小可用的 Skill 定义。"""
    return {
        "prompt": f"你是 Skill {skill_id}。根据用户意图提供相应服务。",
        "skill": {"skill_id": skill_id, "name": skill_id, "version": "V0.0.0-fallback"},
        "tools": [],
        "source": "fallback",
        "mtime": time.time(),
    }


def list_skill_files() -> List[Dict[str, Any]]:
    """列出所有 JSON 格式的 Skill 文件。"""
    result = []
    for fname in os.listdir(_SKILLS_DIR):
        if fname.endswith(".json"):
            try:
                fpath = os.path.join(_SKILLS_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    sk = json.load(f)
                result.append({
                    "file": fname,
                    "skill_id": sk.get("skill_id", fname.replace(".json", "")),
                    "name": sk.get("name", ""),
                    "version": sk.get("version", ""),
                    "has_field_model": bool(sk.get("field_model")),
                })
            except Exception:
                pass
    return result


def clear_cache(skill_id: str = None):
    """清除缓存（可选：指定 skill_id 清除单个，否则清除全部）。"""
    if skill_id:
        _cache.pop(skill_id, None)
    else:
        _cache.clear()


def save_skill_json(skill_id: str, skill_def: Dict[str, Any]) -> bool:
    """保存 Skill 定义到 JSON 文件。

    skill_def 为 {"skill_id": ..., "name": ..., ...} 格式。
    支持两种文件结构：
    - 旧格式: {"skill": {...}, "tools": [...], "prompt": "..."}
    - 新格式: 顶层即为 skill 定义
    """
    try:
        json_path = _get_json_path(skill_id)
        existing: Dict[str, Any] = {}
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)

        # 判断现有文件结构
        if "skill" in existing and isinstance(existing["skill"], dict):
            # 旧格式：更新 skill 子对象
            existing["skill"].update(skill_def)
        else:
            # 新格式：顶层即为 skill 定义，直接 update 顶层
            existing.update(skill_def)

        # 确保 tools / prompt 字段存在
        if "tools" not in existing:
            existing["tools"] = []
        if "prompt" not in existing:
            existing["prompt"] = ""

        # 确保 skill_id 正确
        existing["skill_id"] = skill_id

        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        import logging
        logging.getLogger("skill_loader").error("save_skill_json failed: %s", e)
        return False


# ── 初始化：确保 skills 目录存在 ──
if not os.path.isdir(_SKILLS_DIR):
    os.makedirs(_SKILLS_DIR, exist_ok=True)
