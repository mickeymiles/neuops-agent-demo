# -*- coding: utf-8 -*-
"""投标业务引擎：拆标(规则粗筛+LLM精提炼) / 生成(模板+知识库RAG) / 自检(清单核对) / 导出

复用现有体系：
- LLM：DeepSeek（读取与 agent_chat 相同 key，调用轨迹写入 llm_calls 观测表）
- RAG：app.knowledge.search_knowledge（Chroma 向量检索，降级关键词）
- 文本抽取：app.knowledge.parse_document（docx/pdf/xlsx/txt）
"""
import json
import os
import re
import time
import uuid

import httpx

from .. import config, db, knowledge

# 投标工作台成果根目录
BID_UPLOAD_ROOT = os.path.join(config.BASE_DIR, "uploads", "bid")

# 投标知识库名称（预置 5 类，seed 时按 name 建立；id 由 db_create_knowledge_base 生成）
BID_KB_NAMES = ("投标-资质库", "投标-业绩库", "投标-素材库", "投标-模板库", "投标-人员库")

# 拆标六类章节 → 正则关键词（规则粗筛用）
SECTION_KEYWORDS = {
    "qualifications": ["资格要求", "资质要求", "资格条件", "准入条件", "投标人资格", "投标人资质", "资格标准"],
    "performance": ["业绩要求", "类似项目", "同类项目", "业绩证明", "成功案例", "项目案例"],
    "tech_params": ["技术参数", "技术需求", "货物需求", "功能需求", "技术指标", "★", "▲", "关键技术"],
    "scoring": ["评分标准", "评分细则", "评审标准", "评标办法", "评标细则", "评分办法", "得分"],
    "rejection_clauses": ["废标", "否决", "无效投标", "作废", "拒绝投标", "取消资格"],
}

LLM_CHUNK_SIZE = 6000  # 拆标分块（字符）

# 生成材料类型
DOC_TYPES = {
    "tech_proposal": "技术方案建议书",
    "response": "招标点对点应答",
    "ppt_outline": "售前汇报PPT大纲",
    "impl_plan": "运维实施方案",
}

LLM_JSON_SCHEMA_HINT = """输出严格 JSON（不要输出其他内容），格式：
{
  "qualifications": [{"item": "资质名称", "level": "等级要求", "required_docs": "所需证明材料", "source": "原文出处"}],
  "performance": [{"item": "业绩要求描述", "requirement": "量化要求", "evidence": "证明材料", "source": "原文出处"}],
  "tech_params": [{"item": "参数项", "value": "要求值", "acceptance": "验收方式", "is_key": true/false, "source": "原文出处"}],
  "scoring": [{"item": "评分项", "score": 分值, "notes": "评分说明", "source": "原文出处"}],
  "rejection_clauses": ["废标/否决条款原文摘要"],
  "response_checklist": [{"id": "R1", "item": "应答材料项", "doc_type": "材料类型", "status": "todo", "source": "原文出处"}]
}
"""


# ────────────────────────────────────────────
# 知识库 id 解析
# ────────────────────────────────────────────

def get_bid_kb_ids():
    """按名称解析 5 类投标知识库 id（未创建则返回已存在的子集）"""
    ids = []
    for name in BID_KB_NAMES:
        for kb in db.db_list_knowledge_bases():
            if kb.get("name") == name:
                ids.append(kb["id"])
                break
    return ids


# ────────────────────────────────────────────
# 规则粗筛（不依赖 LLM，TC-2 兜底）
# ────────────────────────────────────────────

def _section_candidates(text: str) -> dict:
    """按行关键词匹配，产出六类骨架：每类最多 N 条候选句"""
    out = {k: [] for k in SECTION_KEYWORDS}
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for k, kws in SECTION_KEYWORDS.items():
        hits = [ln[:120] for ln in lines if any(kw in ln for kw in kws)]
        # 去重保序
        seen, kept = set(), []
        for h in hits:
            if h not in seen:
                seen.add(h)
                kept.append(h)
            if len(kept) >= 6:
                break
        out[k] = kept
    return out


def rule_parse(text: str) -> dict:
    """规则粗筛：产出六类结构化骨架，缺项标「未识别」"""
    cand = _section_candidates(text)
    quals = [{"item": c, "level": "未识别", "required_docs": "未识别", "source": "规则粗筛"}
             for c in cand["qualifications"]] or \
            [{"item": "未识别", "level": "未识别", "required_docs": "未识别", "source": "规则粗筛"}]
    perfs = [{"item": c, "requirement": "未识别", "evidence": "未识别", "source": "规则粗筛"}
             for c in cand["performance"]] or \
            [{"item": "未识别", "requirement": "未识别", "evidence": "未识别", "source": "规则粗筛"}]
    techs = [{"item": c, "value": "未识别", "acceptance": "未识别",
              "is_key": ("★" in c or "▲" in c), "source": "规则粗筛"}
             for c in cand["tech_params"]] or \
            [{"item": "未识别", "value": "未识别", "acceptance": "未识别",
              "is_key": False, "source": "规则粗筛"}]
    scorings = [{"item": c, "score": 0, "notes": "未识别", "source": "规则粗筛"}
                for c in cand["scoring"]] or \
               [{"item": "未识别", "score": 0, "notes": "未识别", "source": "规则粗筛"}]
    checklist = [{"id": f"R{i+1}", "item": c, "doc_type": "证明文件",
                  "status": "todo", "source": "规则粗筛"}
                 for i, c in enumerate(cand["qualifications"][:3] + cand["performance"][:2])] or \
                [{"id": "R1", "item": "未识别", "doc_type": "未识别",
                  "status": "todo", "source": "规则粗筛"}]
    return {
        "qualifications": quals,
        "performance": perfs,
        "tech_params": techs,
        "scoring": scorings,
        "rejection_clauses": cand["rejection_clauses"] or ["未识别"],
        "response_checklist": checklist,
    }


# ────────────────────────────────────────────
# LLM 精提炼
# ────────────────────────────────────────────

def _load_deepseek_key():
    from ..agent_chat import _load_deepseek_key as _k
    return _k()


def _call_llm_json(system_prompt: str, user_text: str, trace_ctx=None):
    """调用 DeepSeek 返回 JSON dict；失败返回 None（调用轨迹写入观测表）"""
    key = _load_deepseek_key()
    if not key:
        return None
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text[:LLM_CHUNK_SIZE]},
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }
    _t0 = time.time()
    try:
        r = httpx.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        if r.status_code != 200:
            _record_llm(trace_ctx, payload, None, time.time() - _t0, error=f"HTTP {r.status_code}")
            return None
        data = r.json()
        _record_llm(trace_ctx, payload, data, time.time() - _t0)
        content = data["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.S)
        return json.loads(content)
    except Exception as e:
        _record_llm(trace_ctx, payload, None, time.time() - _t0, error=str(e))
        return None


def _record_llm(trace_ctx, payload, resp, latency_s, error=""):
    """写 llm_calls 观测表（复用 agent_chat 的记录函数）"""
    try:
        from ..agent_chat import _record_llm_call as _rec
        _rec(trace_ctx, payload.get("model"), payload, resp, latency_s, error=error)
    except Exception:
        pass


def llm_refine(text: str):
    """分块喂 DeepSeek 按 JSON Schema 提炼；解析失败返回 None"""
    """分块喂 DeepSeek 按 JSON Schema 提炼；解析失败返回 None"""
    chunks = [text[i:i + LLM_CHUNK_SIZE] for i in range(0, len(text or ""), LLM_CHUNK_SIZE)] or [""]
    merged = None
    for i, chunk in enumerate(chunks):
        sys_p = "你是资深招投标解析专家。请从招标文件中提取结构化拆标信息。" + LLM_JSON_SCHEMA_HINT
        got = _call_llm_json(sys_p, chunk, trace_ctx={"stage": "bid_parse", "round_no": i})
        if not got:
            continue
        if merged is None:
            merged = got
        else:
            for k in merged:
                if isinstance(merged[k], list) and isinstance(got.get(k), list):
                    merged[k].extend(got[k])
    return merged


# ────────────────────────────────────────────
# 拆标入口
# ────────────────────────────────────────────

def parse_bid_document(project_id: int) -> dict:
    """拆标：读取已抽取文本 → 规则粗筛 → LLM 精提炼 → 合并保存"""
    proj = db.bid_get_project(project_id)
    if not proj:
        raise ValueError("项目不存在")
    text = _read_extracted_text(project_id)
    rule = rule_parse(text or "")
    refined = llm_refine(text or "")
    if refined:
        # LLM 结果优先，空章节回退规则骨架
        for k in rule:
            if k in refined and refined[k]:
                rule[k] = refined[k]
    # 兜底：保证六类齐全
    for k in rule:
        if not rule[k]:
            rule[k] = [{"item": "未识别", "source": "未识别"}]
    db.bid_save_parse_report(project_id, rule)
    db.bid_set_status(project_id, "已拆标")
    return rule


def _read_extracted_text(project_id) -> str:
    """读取项目抽取文本目录下所有文本（合并）"""
    ext_dir = os.path.join(BID_UPLOAD_ROOT, str(project_id), "extracted")
    parts = []
    if os.path.isdir(ext_dir):
        for fn in sorted(os.listdir(ext_dir)):
            p = os.path.join(ext_dir, fn)
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    parts.append(f.read())
            except Exception:
                continue
    return "\n".join(parts)


# ────────────────────────────────────────────
# 生成材料（模板 + 拆标报告 + 知识库 RAG）
# ────────────────────────────────────────────

def generate_document(project_id: int, doc_type: str) -> dict:
    """生成材料，落盘 outputs/{doc_id}.md，返回 doc 记录 dict"""
    proj = db.bid_get_project(project_id)
    if not proj:
        raise ValueError("项目不存在")
    if doc_type not in DOC_TYPES:
        raise ValueError(f"不支持的材料类型: {doc_type}")
    report = proj.get("parse_report") or {}
    kb_ids = get_bid_kb_ids()
    rag_lines = []
    for q in ("资质要求", "业绩要求", "技术方案要点", "实施方案", "人员配置"):
        for hit in knowledge.search_knowledge(q, kb_ids, top_k=2):
            rag_lines.append(f"- [{hit.get('title')}] {hit.get('summary')}")
    rag_text = "\n".join(rag_lines) or "（知识库暂无相关内容）"

    doc_id = uuid.uuid4().hex[:8]
    title = DOC_TYPES[doc_type]
    body = _build_doc_body(doc_type, proj, report, rag_text)

    output_dir = os.path.join(BID_UPLOAD_ROOT, str(project_id), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, f"{doc_id}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(body)

    doc = {
        "id": doc_id,
        "type": doc_type,
        "title": title,
        "path": md_path,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    db.bid_add_generated_doc(project_id, doc)
    db.bid_set_status(project_id, "已生成")
    return doc


def _build_doc_body(doc_type, proj, report, rag_text) -> str:
    """按类型组装文档正文（无依据项输出【待补充材料】占位，不编造参数）"""
    name = proj.get("name", "本项目")
    tenderee = proj.get("tenderee", "招标方")
    lines = [f"# {name} — {DOC_TYPES[doc_type]}", f"招标方：{tenderee}", ""]

    if doc_type == "tech_proposal":
        lines += ["## 一、项目理解与总体方案", "【待补充材料】请依据拆标报告技术参数逐项展开。", ""]
        lines += ["## 二、技术方案要点"]
        for t in report.get("tech_params") or []:
            item, val = t.get("item", "未识别"), t.get("value", "未识别")
            lines.append(f"- {item}：{val}（验收：{t.get('acceptance', '待补充')}）")
        lines += ["", "## 三、实施方案概述", "【待补充材料】实施周期、资源投入、风险控制待补充。", ""]

    elif doc_type == "response":
        lines += ["## 一、资质响应"]
        for q in report.get("qualifications") or []:
            lines.append(f"- 资质：{q.get('item', '未识别')}（等级 {q.get('level', '未识别')}）→ 我方响应：{q.get('required_docs', '待补充材料')}")
        lines += ["", "## 二、业绩响应"]
        for p in report.get("performance") or []:
            lines.append(f"- {p.get('item', '未识别')}（{p.get('requirement', '未识别')}）→ 我方业绩：{p.get('evidence', '待补充材料')}")
        lines += ["", "## 三、技术参数点对点应答"]
        for t in report.get("tech_params") or []:
            lines.append(f"- {t.get('item', '未识别')}：要求 {t.get('value', '未识别')} → 我方应答：【待补充材料】")

    elif doc_type == "ppt_outline":
        lines += ["## 封面", "项目名称 / 投标单位 / 日期", "",
                  "## 目录", "1. 公司简介  2. 项目理解  3. 技术方案  4. 实施计划  5. 团队与资质  6. 服务承诺", "",
                  "## 1 公司简介", "【待补充材料】公司规模、行业资质、核心优势。", "",
                  "## 2 项目理解", f"面向 {tenderee} 的 {name}，核心诉求见拆标报告评分标准。", "",
                  "## 3 技术方案", "依据技术参数逐项阐述（见拆标报告）。", "",
                  "## 4 实施计划", "【待补充材料】里程碑、资源、风险预案。", "",
                  "## 5 团队与资质", "【待补充材料】项目团队与资质证书清单。", "",
                  "## 6 服务承诺", "【待补充材料】SLA、驻场、售后承诺。"]

    elif doc_type == "impl_plan":
        lines += ["## 一、实施目标", f"围绕 {name} 建设目标，提供从部署到运维的全周期服务。", "",
                  "## 二、实施内容", "【待补充材料】部署架构、环境要求、集成范围。", "",
                  "## 三、项目里程碑", "【待补充材料】分阶段里程碑与交付物。", "",
                  "## 四、运维服务方案", "【待补充材料】巡检、告警、应急、变更管理流程。", "",
                  "## 五、人员配置", "【待补充材料】项目经理、实施工程师、驻场运维人员。", ""]

    lines += ["", "---", "", "## 知识库参考", rag_text]
    lines += ["", "> 本文档由投标工作台生成，为 AI 初稿，请人工复核后使用。"]
    return "\n".join(lines)


# ────────────────────────────────────────────
# 合规自检（清单核对）
# ────────────────────────────────────────────

def check_compliance(project_id: int) -> dict:
    """自检：未响应项 / 废标红线 / 评分点得分建议"""
    proj = db.bid_get_project(project_id)
    if not proj:
        raise ValueError("项目不存在")
    report = proj.get("parse_report") or {}
    docs = proj.get("generated_docs") or []
    text = ""
    for d in docs:
        p = d.get("path", "")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    text += f.read() + "\n"
            except Exception:
                continue

    result = {"unresponded": [], "redlines": [], "scoring": []}

    # 1) 未响应项：应答清单条目是否在生成文本中覆盖
    for c in report.get("response_checklist") or []:
        item = c.get("item", "")
        if not item or item == "未识别":
            continue
        keyword = re.sub(r"[【】（）()\s]", "", item)[:12]
        if keyword and keyword not in re.sub(r"[【】（）()\s]", "", text):
            result["unresponded"].append({"id": c.get("id"), "item": item, "reason": "生成材料中未找到对应内容"})

    # 2) 废标红线：逐条检查是否有应对说明
    for clause in report.get("rejection_clauses") or []:
        if clause == "未识别":
            continue
        kw = re.sub(r"[【】（）()\s]", "", clause)[:10]
        if kw and kw not in re.sub(r"[【】（）()\s]", "", text):
            result["redlines"].append({"clause": clause, "level": "高危", "advice": "必须在应答中正面应对，否则有废标风险"})

    # 3) 评分点得分建议：按覆盖度给分
    for s in report.get("scoring") or []:
        item = s.get("item", "")
        full = s.get("score") or 0
        if not item or item == "未识别":
            continue
        kw = re.sub(r"[【】（）()\s]", "", item)[:12]
        covered = bool(kw) and kw in re.sub(r"[【】（）()\s]", "", text)
        result["scoring"].append({
            "item": item,
            "full_score": full,
            "suggest_score": round(full * 0.85) if covered else 0,
            "advice": "已覆盖，建议补充量化证据" if covered else "未覆盖，需补充该评分点内容",
        })

    db.bid_save_check_result(project_id, result)
    db.bid_set_status(project_id, "已自检")
    return result


# ────────────────────────────────────────────
# 导出
# ────────────────────────────────────────────

def export_document(project_id: int, doc_id: str, fmt: str = "md"):
    """导出成果：md 直接返回路径；docx 渲染后返回路径"""
    proj = db.bid_get_project(project_id)
    if not proj:
        raise ValueError("项目不存在")
    doc = next((d for d in (proj.get("generated_docs") or []) if d.get("id") == doc_id), None)
    if not doc:
        raise ValueError("成果不存在")
    md_path = doc.get("path", "")
    if not os.path.isfile(md_path):
        raise ValueError("成果文件缺失")
    if fmt == "md":
        db.bid_set_status(project_id, "已导出")
        return md_path
    if fmt == "docx":
        from docx import Document
        out_dir = os.path.dirname(md_path)
        out_path = os.path.join(out_dir, f"{doc_id}.docx")
        document = Document()
        for ln in open(md_path, encoding="utf-8").read().splitlines():
            ln = ln.rstrip()
            if not ln.strip():
                continue
            if ln.startswith("### "):
                document.add_heading(ln[4:], level=3)
            elif ln.startswith("## "):
                document.add_heading(ln[3:], level=2)
            elif ln.startswith("# "):
                document.add_heading(ln[2:], level=1)
            elif ln.startswith("- ") or ln.startswith("* "):
                document.add_paragraph(ln[2:], style="List Bullet")
            elif ln.startswith("> "):
                document.add_paragraph(ln[2:], style="Quote")
            else:
                document.add_paragraph(ln)
        document.save(out_path)
        db.bid_set_status(project_id, "已导出")
        return out_path
    raise ValueError(f"不支持的导出格式: {fmt}")
