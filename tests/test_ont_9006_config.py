# -*- coding: utf-8 -*-
"""本体轨参与方/模板配置：直读 9006 contract_compare.db（proc_9006_config）。

覆盖：
  - 库不存在时优雅返回空，不抛异常、不创建垃圾 db 文件
  - 供应商 / 审批人 / 全局抄送 / 邮件模板 的读取与过滤规则
  - 审批人只取启用项；模板跳过 subject+body 全空者（回退默认模板）
  - orbit.config() 优先取 9006 页面配置
"""
import os
import sqlite3
import tempfile

import pytest

from app.db import proc_9006_config as p9

DDL = [
    """CREATE TABLE procurement_supplier (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, capability TEXT)""",
    """CREATE TABLE procurement_approver (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, enabled INTEGER DEFAULT 1)""",
    """CREATE TABLE procurement_mail_cc (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT)""",
    """CREATE TABLE procurement_mail_template (
        tpl_key TEXT PRIMARY KEY, name TEXT, subject TEXT, body TEXT, enabled INTEGER DEFAULT 1)""",
]


@pytest.fixture
def db(monkeypatch):
    """建一个临时 9006 库，并把 PROC_9006_DB_PATH 指过去"""
    path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(path)
    for d in DDL:
        conn.execute(d)
    conn.commit()
    conn.close()
    monkeypatch.setenv("PROC_9006_DB_PATH", path)
    yield path
    monkeypatch.delenv("PROC_9006_DB_PATH", raising=False)
    try:
        os.remove(path)
    except OSError:
        pass


def _rows(path, table):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM %s" % table).fetchall()
    conn.close()
    return [dict(x) for x in r]


# ── 容错：库缺失 ────────────────────────────────────────────────
def test_missing_db_returns_empty_without_creating_file(monkeypatch):
    missing = tempfile.mktemp(suffix="_nope.db")
    monkeypatch.setenv("PROC_9006_DB_PATH", missing)
    assert p9.load_suppliers() == []
    assert p9.load_approvers() == []
    assert p9.load_global_cc() == []
    assert p9.load_mail_templates() == {}
    assert p9.supplier_name_map() == {}
    # 关键：不得因为读取动作而凭空创建出空库文件
    assert not os.path.exists(missing), "读取不应创建缺失的 db 文件"


# ── 供应商 ─────────────────────────────────────────────────────
def test_load_suppliers(db):
    conn = sqlite3.connect(db)
    conn.executemany("INSERT INTO procurement_supplier(name,email) VALUES(?,?)",
                     [("中软国际", "s1@corp.com"), ("神州数码", "s2@corp.com"),
                      ("空邮箱", "")])
    conn.commit()
    conn.close()
    got = p9.load_suppliers()
    assert [s["email"] for s in got] == ["s1@corp.com", "s2@corp.com"], "应跳过空邮箱"
    assert p9.supplier_name_map() == {"s1@corp.com": "中软国际", "s2@corp.com": "神州数码"}


def test_supplier_name_map_is_lowercase_key(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO procurement_supplier(name,email) VALUES(?,?)", ("A", "AbC@X.com"))
    conn.commit()
    conn.close()
    assert "abc@x.com" in p9.supplier_name_map()


# ── 审批人：仅启用 ──────────────────────────────────────────────
def test_load_approvers_only_enabled(db):
    conn = sqlite3.connect(db)
    conn.executemany("INSERT INTO procurement_approver(name,email,enabled) VALUES(?,?,?)",
                     [("李审批", "on@corp.com", 1), ("停用的人", "off@corp.com", 0)])
    conn.commit()
    conn.close()
    assert p9.load_approvers() == ["on@corp.com"], "审批人只应取启用中的"


# ── 全局抄送 ────────────────────────────────────────────────────
def test_load_global_cc(db):
    conn = sqlite3.connect(db)
    conn.executemany("INSERT INTO procurement_mail_cc(name,email) VALUES(?,?)",
                     [("监督", "cc1@corp.com"), ("审计", "cc2@corp.com")])
    conn.commit()
    conn.close()
    assert p9.load_global_cc() == ["cc1@corp.com", "cc2@corp.com"]


# ── 邮件模板：跳过全空 ──────────────────────────────────────────
def test_load_mail_templates_skips_blank_and_disabled(db):
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO procurement_mail_template(tpl_key,name,subject,body,enabled) VALUES(?,?,?,?,?)",
        [("A", "回执", "主题A", "正文A", 1),
         ("B", "询价", "", "", 1),          # 全空 -> 回退默认，不覆盖
         ("C", "只有正文", "", "仅正文C", 1),
         ("D", "停用", "主题D", "正文D", 0)])  # 停用 -> 忽略
    conn.commit()
    conn.close()
    got = p9.load_mail_templates()
    assert set(got.keys()) == {"A", "C"}, "B 全空应跳过、D 停用应忽略"
    assert got["A"] == {"subject": "主题A", "body": "正文A"}
    assert got["C"] == {"subject": "", "body": "仅正文C"}, "只填正文时主题留空由默认补齐"


# ── orbit.config() 优先取 9006 页面配置 ──────────────────────────
def test_orbit_config_prefers_9006_page_config(db, monkeypatch):
    monkeypatch.setenv("ONT_SUPPLIERS", "env厂商:env@corp.com")
    monkeypatch.setenv("ONT_APPROVERS", "env-approver@corp.com")
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO procurement_supplier(name,email) VALUES(?,?)", ("页面厂商", "page@corp.com"))
    conn.execute("INSERT INTO procurement_approver(name,email,enabled) VALUES(?,?,1)",
                 ("页面审批人", "page-approver@corp.com"))
    conn.commit()
    conn.close()

    from app.ontology import orbit
    cfg = orbit.config()
    assert cfg["suppliers"] == [{"name": "页面厂商", "email": "page@corp.com"}], \
        "9006 页面配置应优先于 ONT_SUPPLIERS 环境变量"
    assert cfg["approvers"] == ["page-approver@corp.com"], \
        "9006 页面审批人应优先于 ONT_APPROVERS 环境变量"


def test_orbit_config_falls_back_when_page_empty(monkeypatch):
    """页面未配置时不得炸，应完整回退旧链路（与 _legacy_config() 结果一致）。

    注意：app.config 的 ONT_SUPPLIERS/ONT_APPROVERS 在 import 时即固化，
    运行期 monkeypatch 环境变量不会生效，故这里断言「等于旧链路结果」而非具体值。
    """
    missing = tempfile.mktemp(suffix="_nope.db")
    monkeypatch.setenv("PROC_9006_DB_PATH", missing)

    from app.ontology import orbit
    cfg = orbit.config()
    legacy = orbit._legacy_config()
    assert cfg == legacy, "页面为空时应完全回退到旧链路"
    assert legacy["suppliers"], "旧链路应能给出供应商（否则回退无意义）"
    assert legacy["approvers"], "旧链路应能给出审批人（否则回退无意义）"
