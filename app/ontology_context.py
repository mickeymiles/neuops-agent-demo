# -*- coding: utf-8 -*-
"""本体语义装载层（★emp-006 试点：把 LLM 锚定到本体，而非手写工具提示词）。

设计目标：
- 不再给员工一长串手写「工具描述」当世界模型；改为把 ontos 的 TBox/ABox 声明
  （实体/关系/函数/动作 + 各自的 reasoning 推理指引）序列化成系统提示的【本体语义】段落。
- 员工只持有 3 个薄通用原语（ontology_compute / ontology_read / ontology_act），
  工具描述极简，业务含义全部来自本体语义段落。
- 语义真相在 ontos 单一来源：本体一改，员工自动看见，不再漂移。
"""
import os
import sys

# 共享 ontos 子模块位于 <repo>/ontos（内含 ontos/ 包）
_ONTOS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ontos"))


def _biz():
    """返回共享本体 TBox 模块（ontos.domain_business），懒加载并补齐 import 路径。"""
    if _ONTOS_ROOT not in sys.path:
        sys.path.insert(0, _ONTOS_ROOT)
    from ontos import domain_business as biz
    return biz


# ═══════════════════════════════════════════════════════════════════════
# 试点范围：哪些员工采用本体锚定，以及暴露哪些语义切片。
# 后续推广时，把白名单迁到 employees 表的 ontology_scope 字段即可，本字典作废。
# ═══════════════════════════════════════════════════════════════════════
EMP_ONTOLOGY_SCOPE: dict = {
    "emp-006": {
        "domains": ["financial"],                       # 只暴露财务域函数（成本/预警/ROI…）
        "relations_keywords": ["成本", "预警", "预估", "项目", "合同"],
        "include_actions": True,
    },
}


def is_ontology_grounded(emp_id: str) -> bool:
    """该员工是否采用本体锚定（取代手写工具提示词）。"""
    return emp_id in EMP_ONTOLOGY_SCOPE


def build_ontology_context(emp_id: str) -> str:
    """把本体声明序列化为【本体语义】markdown 段落，注入员工系统提示。

    内容来自 ontos.to_spec()（运行期只读导出），按员工 scope 过滤：
    函数(含 description + reasoning 推理指引 + 输入/输出)、关系、动作(条件/不变量)、
    成本策略核心推理。这是员工推理的唯一权威依据。
    """
    scope = EMP_ONTOLOGY_SCOPE.get(emp_id)
    if not scope:
        return ""
    spec = _biz().to_spec()
    domains = set(scope.get("domains", []))
    rel_kw = scope.get("relations_keywords", [])
    lines: list = []

    lines.append("## 本体语义（你推理的权威依据）")
    lines.append("以下实体/关系/函数/动作/策略由本体(TBox/ABox)固化声明，"
                 "所有含义与判定规则以此为准，不得用你自己的假设替代。")

    # ── 成本策略核心推理（给 LLM 的口径总纲）──
    cf = (spec.get("policies") or {}).get("costFormula", {}) or {}
    if cf.get("reasoning"):
        lines.append("\n### 成本口径核心推理")
        lines.append(cf["reasoning"])

    # ── 知识层：判定标准与治理要求（「该怎么判」；与本体「能不能说」分离）──
    kn = spec.get("knowledge") or {}
    if kn.get("available") and kn.get("policies"):
        lines.append("\n### 知识/策略（判定标准与治理要求 · 唯一真源在知识层）")
        lines.append("以下阈值、口径与治理要求由知识层统一管理（含版本 / 责任人 / 生效期），"
                     "判定项目时必须以此为准，不得自行设定阈值或凭印象下结论；"
                     "知识层未覆盖的判定，才可用本体语义推演。")
        for pid, p in kn["policies"].items():
            head = f"- **{p.get('name')}** (`{pid}`) · {p.get('kind')} · v{p.get('version')}"
            if p.get("owner"):
                head += f"　责任：{p['owner']}"
            if p.get("effective_from") or p.get("effective_to"):
                head += f"　生效：{p.get('effective_from') or '不限'} ~ {p.get('effective_to') or '不限'}"
            lines.append(head)
            if p.get("params"):
                lines.append("  - 判定参数：" + "、".join(
                    f"{k}={v}" for k, v in p["params"].items()))
            for r in (p.get("rules") or []):
                lines.append(f"  - {r}")
            if p.get("description"):
                lines.append(f"  - 说明：{p['description']}")

    # ── 函数（按域过滤）──
    funcs = [f for f in spec.get("functions", []) if (not domains or f.get("domain") in domains)]
    if funcs:
        lines.append("\n### 可用函数（用 ontology_compute 调用，id 即函数名）")
        for f in funcs:
            lines.append(f"- **{f.get('name')}** (`{f['id']}`)：{f.get('description', '')}")
            if f.get("reasoning"):
                lines.append(f"  - 推理指引：{f['reasoning']}")
            if f.get("inputs"):
                lines.append(f"  - 输入：{', '.join(f['inputs'])}")
            if f.get("outputs"):
                lines.append(f"  - 输出：{', '.join(f['outputs'])}")

    # ── 关系（按关键字过滤）──
    rels = spec.get("relations", {}) or {}
    if rel_kw:
        rels = {k: v for k, v in rels.items() if any(w in v for w in rel_kw)}
    if rels:
        lines.append("\n### 关键关系")
        for k, v in rels.items():
            lines.append(f"- `{k}`：{v}")

    # ── 动作（含护栏）──
    if scope.get("include_actions"):
        acts = spec.get("actions", []) or []
        if acts:
            lines.append("\n### 可用动作（用 ontology_act 触发，先经护栏校验）")
            for a in acts:
                lines.append(f"- **{a.get('name')}**：{a.get('definition', '')}")
                if a.get("conditions"):
                    lines.append(f"  - 前置条件：{'; '.join(a['conditions'])}")
                if a.get("invariants"):
                    lines.append(f"  - 不变量：{'; '.join(a['invariants'])}")

    return "\n".join(lines)
