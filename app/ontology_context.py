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
    """把本体声明序列化为【本体语义·索引】markdown 段落，注入员工系统提示。

    设计：只灌「索引」（每个函数/策略/动作列 id + 一句话用途 + 签名），不灌长字段
    （函数的 reasoning 推理指引、策略的 params/rules 判定参数）。这些完整定义由 agent
    在调用前经 ontology_read(kind, id) 按需懒加载——避免上下文随本体规模 O(N) 膨胀，
    且单条查询只取用到的 1~2 条，其余不陪跑。

    内容来自 ontos.to_spec()（运行期只读导出），按员工 scope 过滤。
    """
    scope = EMP_ONTOLOGY_SCOPE.get(emp_id)
    if not scope:
        return ""
    spec = _biz().to_spec()
    domains = set(scope.get("domains", []))
    rel_kw = scope.get("relations_keywords", [])
    lines: list = []

    lines.append("## 本体语义（你推理的权威依据 · 索引版）")
    lines.append("以下为本体(TBox/ABox)与知识层的【索引】，每个函数/策略只列 id 与一句话用途。"
                 "调用前请用 **ontology_read(kind='function'|'policy'|'entity'|'action', id=...)** "
                 "取该条的【完整定义 / 推理指引 / 判定参数】，再执行——不要凭索引里的只言片语臆测。")

    # ── 成本策略核心推理（全局口径总纲，短，预灌）──
    cf = (spec.get("policies") or {}).get("costFormula", {}) or {}
    if cf.get("reasoning"):
        lines.append("\n### 成本口径核心推理（全局总纲）")
        lines.append(cf["reasoning"])

    # ── 知识层索引（独立层；不灌 params/rules，按需经 ontology_read 取）──
    kn = spec.get("knowledge") or {}
    if kn.get("available") and kn.get("policies"):
        lines.append("\n### 知识层（独立层 · 判定标准与治理要求）")
        lines.append("知识层与本体层分离，统一管阈值/口径/治理。以下为索引；"
                     "用 ontology_read(kind='policy', id=<策略id>) 取完整参数与规则后再判定。")
        for pid, p in kn["policies"].items():
            head = f"- `{pid}` · {p.get('kind')} · v{p.get('version')}"
            if p.get("owner"):
                head += f"　责任：{p['owner']}"
            if p.get("effective_from") or p.get("effective_to"):
                head += f"　生效：{p.get('effective_from') or '不限'} ~ {p.get('effective_to') or '不限'}"
            lines.append(head)
            if p.get("description"):
                lines.append(f"  - 用途：{p['description']}")

    # ── 函数索引（按域过滤；不灌 reasoning，按需取）──
    funcs = [f for f in spec.get("functions", []) if (not domains or f.get("domain") in domains)]
    if funcs:
        lines.append("\n### 可用函数（用 ontology_compute 调用，id 即函数名）")
        lines.append("调用前先用 ontology_read(kind='function', id=<函数id>) 取该函数的推理指引。")
        for f in funcs:
            line = f"- `{f['id']}`：{f.get('description', '')}"
            sig = []
            if f.get("inputs"):
                sig.append("入:" + ",".join(f["inputs"]))
            if f.get("outputs"):
                sig.append("出:" + ",".join(f["outputs"]))
            if sig:
                line += "  [" + " · ".join(sig) + "]"
            lines.append(line)

    # ── 关系（按关键字过滤；短，预灌）──
    rels = spec.get("relations", {}) or {}
    if rel_kw:
        rels = {k: v for k, v in rels.items() if any(w in v for w in rel_kw)}
    if rels:
        lines.append("\n### 关键关系")
        for k, v in rels.items():
            lines.append(f"- `{k}`：{v}")

    # ── 动作索引（含护栏；不灌条件/不变量，按需取）──
    if scope.get("include_actions"):
        acts = spec.get("actions", []) or []
        if acts:
            lines.append("\n### 可用动作（用 ontology_act 触发，先经护栏校验）")
            lines.append("需看前置条件/不变量时，ontology_read(kind='action', id=<动作id>) 取完整定义。")
            for a in acts:
                lines.append(f"- `{a.get('name')}`：{a.get('definition', '')}")

    return "\n".join(lines)
