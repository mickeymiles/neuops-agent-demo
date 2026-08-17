#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投标知识库种子数据（来自 mock_data.py MOCK_BID_KB / MOCK_BID_TEMPLATES）。
在 49 上真实向量化入库，作为 007 投标专家的知识库。"""

# 历史投标方案 / 中标库
BID_DOCS = [
    {
        "id": "KB-001",
        "industry": "金融/银行",
        "scenario": "一体化运维平台建设",
        "title": "某银行一体化运维平台技术方案",
        "summary": "全栈监控+告警降噪+自动化运维一体化方案，中标金额680万",
        "amount": 680, "win": True,
        "keywords": ["银行", "监控", "运维平台", "告警", "自动化"],
        "content": "方案围绕银行核心系统统一监控（服务器/数据库/中间件/网络）、智能告警降噪、自动化巡检与自愈展开，含4层可观测体系与7大数字员工建设路径，满足金融行业合规要求。",
    },
    {
        "id": "KB-002",
        "industry": "政务",
        "scenario": "云监控体系建设",
        "title": "某政务云监控体系建设方案",
        "summary": "政务云资源纳管+网络探测+合规审计方案，中标金额420万",
        "amount": 420, "win": True,
        "keywords": ["政务云", "纳管", "网络探测", "合规"],
        "content": "方案聚焦政务云资源统一纳管、网络设备探测、安全合规审计与属地化交付。",
    },
    {
        "id": "KB-003",
        "industry": "制造",
        "scenario": "IT运维外包",
        "title": "某制造企业IT运维外包方案",
        "summary": "驻场运维+SLA分级响应+季度巡检报告体系，中标金额195万",
        "amount": 195, "win": True,
        "keywords": ["外包", "驻场", "SLA", "巡检"],
        "content": "方案包含驻场服务团队、SLA分级响应、季度巡检与考核指标看板。",
    },
    {
        "id": "KB-004",
        "industry": "能源",
        "scenario": "一体化运维项目",
        "title": "某能源集团一体化运维方案（未中标）",
        "summary": "因报价过高未中标，技术部分获评优秀",
        "amount": 0, "win": False,
        "keywords": ["能源", "运维", "集团"],
        "content": "方案技术部分获评优秀，商务报价高于竞争对手12%，复盘结论：控制集成类成本报价。",
    },
    {
        "id": "KB-005",
        "industry": "医疗",
        "scenario": "智慧运维升级",
        "title": "某医院智慧运维升级方案（编写中）",
        "summary": "基于统一监控平台叠加AI运维能力，含等保合规改造",
        "amount": 0, "win": False,
        "keywords": ["医院", "智慧运维", "等保", "AI"],
        "content": "方案含等保合规改造、智慧运维能力升级与医疗核心系统专项保障。",
    },
]

# 投标标准模板库 / 技术规范模板（也作为可检索知识）
TEMPLATE_DOCS = [
    {
        "id": "TPL-tech_proposal",
        "industry": "模板",
        "scenario": "技术方案建议书",
        "title": "技术方案建议书模板 v2.3",
        "summary": "标准技术方案建议书章节结构",
        "amount": 0, "win": True,
        "keywords": ["技术方案", "建议书", "模板"],
        "content": "章节：项目背景与需求理解、总体架构设计、功能方案说明、技术指标响应、实施与服务保障、项目团队与资质。",
    },
    {
        "id": "TPL-response",
        "industry": "模板",
        "scenario": "招标应答",
        "title": "招标点对点应答模板 v1.8",
        "summary": "标准招标应答结构",
        "amount": 0, "win": True,
        "keywords": ["招标", "应答", "偏离表"],
        "content": "章节：商务应答、技术应答、偏离表、证明材料索引。",
    },
    {
        "id": "TPL-ppt_outline",
        "industry": "模板",
        "scenario": "售前汇报",
        "title": "售前汇报PPT大纲模板 v2.0",
        "summary": "标准售前汇报 PPT 大纲",
        "amount": 0, "win": True,
        "keywords": ["PPT", "售前", "汇报", "大纲"],
        "content": "章节：封面与公司简介、客户痛点与需求理解、方案总体架构、核心亮点、实施路径、成功案例、Q&A。",
    },
    {
        "id": "TPL-impl_plan",
        "industry": "模板",
        "scenario": "实施方案",
        "title": "实施方案模板 v1.5",
        "summary": "标准实施方案结构",
        "amount": 0, "win": True,
        "keywords": ["实施", "方案", "验收"],
        "content": "章节：项目范围与目标、实施组织与计划、详细实施步骤、风险管理、验收标准与交付物。",
    },
]

ALL_DOCS = BID_DOCS + TEMPLATE_DOCS


def doc_to_text(d):
    return " ".join([
        d["industry"], d["scenario"], d["title"], d["summary"],
        " ".join(d["keywords"]), d["content"],
    ])
