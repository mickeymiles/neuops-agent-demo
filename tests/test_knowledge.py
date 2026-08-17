# -*- coding: utf-8 -*-
"""知识库与 RAG 测试：文档解析 / 切块 / 分词 / 关键词降级检索
# 规格编号: NO-008 知识库与 RAG（解析/切块/分词/关键词降级检索）
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl  # noqa: E402
import pytest  # noqa: E402

from app import db  # noqa: E402
from app.knowledge import (  # noqa: E402
    _keyword_search,
    _tokenize_zh,
    chunk_text,
    parse_document,
    search_knowledge,
)


def _uniq_kb():
    return "kb-test-" + uuid.uuid4().hex[:8]


# ==================== parse_document ====================

def test_parse_document_txt(tmp_path):
    p = tmp_path / "说明.txt"
    p.write_text("订单服务使用说明：支持重启与滚动发布。", encoding="utf-8")
    assert parse_document(str(p)) == "订单服务使用说明：支持重启与滚动发布。"


def test_parse_document_md(tmp_path):
    p = tmp_path / "guide.md"
    p.write_text("# 标题\n\n正文内容。", encoding="utf-8")
    assert parse_document(str(p)) == "# 标题\n\n正文内容。"


def test_parse_document_xlsx(tmp_path):
    """xlsx 解析：工作表标记 + 列名: 值 行"""
    p = tmp_path / "台账.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "服务台账"
    ws.append(["服务名", "端口"])
    ws.append(["订单服务", 8080])
    wb.save(str(p))
    wb.close()

    text = parse_document(str(p))
    assert "## 工作表: 服务台账" in text
    assert "服务名: 订单服务；端口: 8080" in text


def test_parse_document_unsupported_extension(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"not supported")
    assert parse_document(str(p)) == ""


# ==================== chunk_text ====================

def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_short_paras_aggregated():
    """多个短段落聚合到一个块（小于 chunk_size）"""
    text = "第一段。\n\n第二段。\n\n第三段。"
    chunks = chunk_text(text, chunk_size=400, overlap=50)
    assert len(chunks) == 1
    assert "第一段。" in chunks[0] and "第三段。" in chunks[0]


def test_chunk_text_long_split_with_overlap():
    """超长文本按 chunk_size 切块，相邻块带重叠"""
    text = "长" * 100
    chunks = chunk_text(text, chunk_size=30, overlap=5)
    assert len(chunks) >= 3
    assert all(len(c) <= 30 for c in chunks)
    # 相邻块重叠 overlap 个字符
    for i in range(len(chunks) - 1):
        assert chunks[i + 1].startswith(chunks[i][-5:])


def test_chunk_text_short_fragments_filtered():
    """全部碎片长度 < 8 → 过滤为空"""
    assert chunk_text("短" * 7, chunk_size=400, overlap=50) == []


# ==================== _tokenize_zh ====================

def test_tokenize_zh_short_word():
    """词长 ≤ 4：整体计频 +2"""
    freq = _tokenize_zh("订单服务")
    assert freq.get("订单服务") == 2


def test_tokenize_zh_long_word_window():
    """长词按 4/3/2 字滑动窗口计频"""
    freq = _tokenize_zh("数据库连接池监控")
    assert freq  # 非空
    assert "数据库连" in freq  # 4 字窗口命中
    assert any(len(w) == 4 and freq[w] == 4 for w in freq)


def test_tokenize_zh_punctuation_split():
    freq = _tokenize_zh("订单，服务")
    assert "订单" in freq
    assert "服务" in freq


# ==================== _keyword_search（真实 db 隔离） ====================

def test_keyword_search_ranking():
    kb_id = _uniq_kb()
    try:
        db.db_add_kb_chunks(kb_id, "doc1.txt", ["订单服务响应缓慢，需要排查", "支付模块日志异常"])
        db.db_add_kb_chunks(kb_id, "doc2.txt", ["网络延迟说明文档"])
        results = _keyword_search("订单服务", [kb_id], top_k=3)
        assert results
        assert results[0]["title"] == "doc1.txt"
        assert 0 < results[0]["score"] < 1
        assert results[0]["source"] == "doc1.txt"
        assert results[0]["summary"].startswith("订单服务")
    finally:
        db.db_clear_kb_chunks(kb_id)


def test_keyword_search_no_match():
    kb_id = _uniq_kb()
    try:
        db.db_add_kb_chunks(kb_id, "doc1.txt", ["完全无关的内容甲"])
        assert _keyword_search("查询不到的东西", [kb_id], top_k=3) == []
    finally:
        db.db_clear_kb_chunks(kb_id)


# ==================== search_knowledge ====================

def test_search_knowledge_empty_input():
    assert search_knowledge("", ["kb-x"], top_k=5) == []
    assert search_knowledge("问题", [], top_k=5) == []


def test_search_knowledge_fallback_keyword():
    """向量库不可用时降级关键词检索，仍能返回命中条目"""
    kb_id = _uniq_kb()
    try:
        db.db_add_kb_chunks(kb_id, "doc1.txt", ["MySQL 慢查询优化建议与索引策略"])
        results = search_knowledge("MySQL 慢查询", [kb_id], top_k=3)
        assert results
        assert results[0]["title"] == "doc1.txt"
        assert "MySQL" in results[0]["summary"]
    finally:
        db.db_clear_kb_chunks(kb_id)
