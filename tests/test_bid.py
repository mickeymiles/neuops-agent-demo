# -*- coding: utf-8 -*-
"""投标工作台测试：项目管理 / 上传 / 拆标 / 生成 / 自检 / 导出 / 聊天联动
# 规格编号: NO-009 FR-1~FR-7 / NFR-1 / TC-2
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)

BID_TXT = (
    "一、资质要求：投标人须具备 ISO9001 质量管理体系认证资质，并提供证书复印件。\n"
    "二、业绩要求：投标人近 3 年须具有同类政务云运维项目业绩不少于 2 个，提供合同与验收报告。\n"
    "三、技术参数：CPU 主频不低于 3.0GHz，内存不小于 64GB（★关键参数）。\n"
    "四、评分标准：技术方案完整性 20 分，项目业绩 15 分。\n"
    "五、废标条款：投标文件未按要求密封的，作废标处理。\n"
)


def _mk_project(name="测试投标项目"):
    r = client.post("/api/bid/projects", json={"name": name, "tenderee": "某市采购中心",
                                               "industry": "政务", "budget": 500, "deadline": "2026-09-30"})
    assert r.status_code == 200
    return r.json()["project"]


def _upload(pid, content="", name="规范书.txt"):
    files = {"files": (name, content.encode("utf-8"), "text/plain")}
    return client.post(f"/api/bid/projects/{pid}/upload", files=files)


# ==================== FR-1 项目管理 ====================

def test_bid_project_crud():
    # NO-009 FR-1: 新建
    p = _mk_project("CRUD项目")
    pid = p["id"]
    assert p["status"] == "草稿"
    assert p["tenderee"] == "某市采购中心"
    # 列表
    r = client.get("/api/bid/projects")
    assert any(x["id"] == pid for x in r.json()["projects"])
    # 更新
    r = client.patch(f"/api/bid/projects/{pid}", json={"industry": "金融"})
    assert r.json()["project"]["industry"] == "金融"
    # 详情
    r = client.get(f"/api/bid/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["project"]["id"] == pid
    # 删除
    r = client.delete(f"/api/bid/projects/{pid}")
    assert r.json()["success"] is True
    assert client.get(f"/api/bid/projects/{pid}").status_code == 404


def test_bid_project_name_required():
    # NO-009 FR-1: 名称必填
    r = client.post("/api/bid/projects", json={"name": "  "})
    assert r.status_code == 400


# ==================== FR-2 上传与文本抽取 ====================

def test_bid_upload_txt():
    # NO-009 FR-2: 上传 txt → 原文件保存 + 文本抽取 + 状态流转
    p = _mk_project("上传项目")
    pid = p["id"]
    r = _upload(pid, BID_TXT)
    assert r.json()["success"] is True
    assert len(r.json()["saved"]) == 1
    detail = client.get(f"/api/bid/projects/{pid}").json()["project"]
    assert detail["status"] == "已上传"
    assert any(f["name"] == "规范书.txt" for f in detail["files"])


def test_bid_upload_unsupported_ext():
    # NO-009 FR-2: 不支持格式应失败
    p = _mk_project("格式项目")
    pid = p["id"]
    files = {"files": ("bad.exe", b"MZ", "application/octet-stream")}
    r = client.post(f"/api/bid/projects/{pid}/upload", files=files)
    assert r.json()["success"] is False
    assert r.json()["failed"]


# ==================== FR-3 拆标解析 ====================

def test_bid_parse_rule_fallback():
    # NO-009 FR-3 / TC-2: 无 LLM 时规则粗筛仍产出六类骨架，缺项标"未识别"
    from app.bidding.bid_engine import rule_parse
    report = rule_parse(BID_TXT)
    for k in ("qualifications", "performance", "tech_params", "scoring",
              "rejection_clauses", "response_checklist"):
        assert k in report
    assert any("ISO9001" in str(x) for x in report["qualifications"])
    assert any("政务云" in str(x) for x in report["performance"])
    assert any("CPU" in str(x) for x in report["tech_params"])
    # 空文本 → 未识别
    empty = rule_parse("")
    assert empty["qualifications"][0]["item"] == "未识别"


def test_bid_parse_api_flow():
    # NO-009 FR-3: 触发拆标 → 报告六类齐全 + 状态"已拆标"
    p = _mk_project("拆标项目")
    pid = p["id"]
    _upload(pid, BID_TXT)
    r = client.post(f"/api/bid/projects/{pid}/parse")
    assert r.status_code == 200
    report = r.json()["report"]
    assert set(report.keys()) >= {"qualifications", "performance", "tech_params",
                                  "scoring", "rejection_clauses", "response_checklist"}
    detail = client.get(f"/api/bid/projects/{pid}").json()["project"]
    assert detail["status"] == "已拆标"


# ==================== FR-4 生成材料 ====================

def test_bid_generate_docs():
    # NO-009 FR-4: 四类材料可生成，无依据项标"待补充材料"
    p = _mk_project("生成项目")
    pid = p["id"]
    _upload(pid, BID_TXT)
    client.post(f"/api/bid/projects/{pid}/parse")
    for doc_type in ("tech_proposal", "response", "ppt_outline", "impl_plan"):
        r = client.post(f"/api/bid/projects/{pid}/generate", json={"type": doc_type})
        assert r.status_code == 200, doc_type
        doc = r.json()["doc"]
        assert doc["type"] == doc_type
        assert os.path.isfile(doc["path"])
        assert os.path.getsize(doc["path"]) > 0
    detail = client.get(f"/api/bid/projects/{pid}").json()["project"]
    assert len(detail["generated_docs"]) == 4
    assert detail["status"] == "已生成"


def test_bid_generate_invalid_type():
    # NO-009 FR-4: 非法材料类型拒绝
    p = _mk_project("非法类型")
    pid = p["id"]
    r = client.post(f"/api/bid/projects/{pid}/generate", json={"type": "unknown"})
    assert r.status_code == 400


# ==================== FR-5 合规自检 ====================

def test_bid_check_compliance():
    # NO-009 FR-5: 自检输出未响应项/红线/评分建议
    p = _mk_project("自检项目")
    pid = p["id"]
    _upload(pid, BID_TXT)
    client.post(f"/api/bid/projects/{pid}/parse")
    client.post(f"/api/bid/projects/{pid}/generate", json={"type": "response"})
    r = client.post(f"/api/bid/projects/{pid}/check")
    assert r.status_code == 200
    result = r.json()["result"]
    assert set(result.keys()) == {"unresponded", "redlines", "scoring"}
    assert isinstance(result["unresponded"], list)
    assert isinstance(result["redlines"], list)
    assert isinstance(result["scoring"], list)
    detail = client.get(f"/api/bid/projects/{pid}").json()["project"]
    assert detail["status"] == "已自检"


# ==================== FR-6 成果导出 ====================

def test_bid_export_md():
    # NO-009 FR-6: 导出 md
    p = _mk_project("导出项目")
    pid = p["id"]
    _upload(pid, BID_TXT)
    client.post(f"/api/bid/projects/{pid}/parse")
    doc = client.post(f"/api/bid/projects/{pid}/generate", json={"type": "ppt_outline"}).json()["doc"]
    r = client.get(f"/api/bid/projects/{pid}/export/{doc['id']}?fmt=md")
    assert r.status_code == 200
    assert "text/markdown" in r.headers.get("content-type", "")
    assert "#" in r.text


def test_bid_export_docx():
    # NO-009 FR-6: 导出 docx
    p = _mk_project("导出docx")
    pid = p["id"]
    _upload(pid, BID_TXT)
    client.post(f"/api/bid/projects/{pid}/parse")
    doc = client.post(f"/api/bid/projects/{pid}/generate", json={"type": "tech_proposal"}).json()["doc"]
    r = client.get(f"/api/bid/projects/{pid}/export/{doc['id']}?fmt=docx")
    assert r.status_code == 200
    assert "wordprocessingml" in r.headers.get("content-type", "")
    assert len(r.content) > 100


# ==================== FR-7 聊天联动 ====================

def test_bid_employee_prompt_guidance():
    # NO-009 FR-7: emp-007 prompt 含工作台跳转指引；其他员工不受影响
    from app.agent_chat import build_employee_prompt
    prompt_007 = build_employee_prompt("emp-007")
    assert "工作台协作边界" in prompt_007
    assert "/bidding" in prompt_007
    prompt_001 = build_employee_prompt("emp-001")
    assert "工作台协作边界" not in prompt_001


# ==================== 页面与知识库 ====================

def test_bidding_page():
    r = client.get("/bidding")
    assert r.status_code == 200
    assert "投标工作台" in r.text


def test_bid_kb_seeded_and_bound():
    # NO-008 delta: 5 类投标知识库已预置且绑定 emp-007
    from app import db as _db
    from app.seed_bid_kb import BID_KB_SEED, EMPLOYEE_ID
    kbs = {kb["name"]: kb for kb in _db.db_list_knowledge_bases()}
    for name in BID_KB_SEED:
        assert name in kbs, f"投标知识库未预置: {name}"
    bound = _db.db_get_employee_kb_ids(EMPLOYEE_ID)
    bound_names = [kb["name"] for kb in _db.db_list_knowledge_bases() if kb["id"] in bound]
    for name in BID_KB_SEED:
        assert name in bound_names, f"{EMPLOYEE_ID} 未绑定: {name}"
