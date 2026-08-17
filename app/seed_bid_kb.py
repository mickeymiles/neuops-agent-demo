# -*- coding: utf-8 -*-
"""投标知识库预置（NO-008 delta / NO-009）：

幂等执行 seed_bid_kb()：
1. 预置 5 类投标知识库（投标-资质库 / 业绩库 / 素材库 / 模板库 / 人员库），
   已存在则复用，不重复创建；
2. 每类写入 1–2 条示例文档到 uploads/{kb_id}/ 并构建索引（向量化，失败降级关键词）；
3. 将 5 类库绑定到 emp-007（先清后写，复用 db_bind_employee_kb）。
"""
import os

from . import config, db, knowledge

# 投标知识库预置定义：name -> 示例文档（title, body）
BID_KB_SEED = {
    "投标-资质库": [
        ("企业资质-ISO体系认证",
         "公司已通过 ISO9001 质量管理体系认证、ISO20000 信息技术服务管理体系认证、"
         "ISO27001 信息安全管理体系认证，可提供认证证书复印件（加盖公章）。"),
        ("企业资质-CMMI能力成熟度",
         "公司软件研发通过 CMMI 5 级认证，具备成熟度最高的软件过程改进能力，"
         "投标时随附 CMMI 认证证书及官方查询截图。"),
    ],
    "投标-业绩库": [
        ("标杆案例-政务云平台运维",
         "近 3 年完成 XX 市政务云平台运维服务项目（合同金额 1200 万元），"
         "提供合同关键页、验收报告与业主联系方式作为业绩证明材料。"),
        ("标杆案例-医院信息化集成",
         "为三甲医院提供信息化系统集成与驻场运维（合同金额 800 万元），"
         "项目按期交付并通过终验，业主评价良好，可提供验收报告。"),
    ],
    "投标-素材库": [
        ("公司简介素材",
         "公司成立于 2010 年，注册资金 5000 万元，员工 600 余人，其中研发与技术人员占比 70%，"
         "专注政务、金融、医疗行业的 IT 服务与运维，服务客户超过 300 家。"),
        ("荣誉与资质素材",
         "荣获高新技术企业证书、软件企业认定证书、AAA 级信用企业；"
         "持有软件著作权 50 余项，专利 10 余项，可附证书扫描件。"),
    ],
    "投标-模板库": [
        ("技术方案建议书模板",
         "技术方案建议书结构：1 项目理解 2 总体技术架构 3 分项技术方案（逐项对应招标技术参数）"
         "4 实施方案（里程碑/资源/风险） 5 质量保障体系 6 售后服务承诺 7 项目团队。"),
        ("招标点对点应答模板",
         "点对点应答模板：逐条摘录招标要求原文 → 标注响应结论（完全响应/部分响应/偏离）"
         "→ 提供支撑材料（技术参数表、产品彩页、证明文件）→ 签署响应承诺。"),
    ],
    "投标-人员库": [
        ("项目经理-张三",
         "张三，高级项目经理（PMP 认证），10 年 IT 项目管理经验，主持过 8 个千万级项目，"
         "近 3 年同类项目 3 个，可提供社保证明、资格证书与项目经历表。"),
        ("技术负责人-李四",
         "李四，系统架构师（系统架构设计师高级职称），15 年技术经验，"
         "主导过政务云平台、大数据平台架构设计，可作为技术负责人岗位人选。"),
    ],
}

EMPLOYEE_ID = "emp-007"


def seed_bid_kb():
    """预置 5 类投标知识库并绑定 emp-007（幂等）"""
    existing = {kb["name"]: kb["id"] for kb in db.db_list_knowledge_bases()}
    kb_ids = []
    for name, docs in BID_KB_SEED.items():
        kb_id = existing.get(name)
        if not kb_id:
            kb_id = db.db_create_knowledge_base(name, f"投标业务-{name.replace('投标-', '')}（预置示例数据）")
            print(f"[seed_bid_kb] 创建知识库: {name} ({kb_id})")
        kb_ids.append(kb_id)
        _seed_docs(kb_id, name, docs)
    # 绑定 emp-007（覆盖为 5 库，先清后写由 db_bind_employee_kb 保证）
    db.db_bind_employee_kb(EMPLOYEE_ID, kb_ids)
    print(f"[seed_bid_kb] 已绑定 {EMPLOYEE_ID} -> {len(kb_ids)} 个投标知识库")
    return kb_ids


def _seed_docs(kb_id, name, docs):
    """幂等写入示例文档：uploads/{kb_id}/ 下无 .md 文件才写入并重建索引"""
    target_dir = os.path.join(knowledge.UPLOAD_DIR, kb_id)
    os.makedirs(target_dir, exist_ok=True)
    has_md = any(fn.endswith(".md") for fn in os.listdir(target_dir))
    if has_md:
        return
    for i, (title, body) in enumerate(docs, start=1):
        fn = os.path.join(target_dir, f"seed-{i:02d}-{title}.md")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{body}\n")
    files = [os.path.join(target_dir, fn) for fn in os.listdir(target_dir) if fn.endswith(".md")]
    result = knowledge.build_kb_index(kb_id, files)
    print(f"[seed_bid_kb] {name}: 文档 {result.get('doc_count')} / 切块 {result.get('chunk_count')} "
          f"/ 向量 {'是' if result.get('vector') else '否(降级关键词)'}")
