# -*- coding: utf-8 -*-
"""数字员工「交互方式」配置 + 启停开关真实生效 单元测试。

覆盖：
- employee_channels 库 CRUD
- GET/PUT /api/employees/{id}/channels：掩码、空密码保留、邮箱必填校验
- 启停开关真正 gate 运行时（needs_exec 受 employees.enabled / 关联技能 enabled 影响）
- mail_gateway._ont_mail_cfg 优先读 employee_channels
"""
import app.config as _cfg
import app.db.base as _base

from fastapi.testclient import TestClient
import app.db as db
from main import app

client = TestClient(app)


def _fresh(monkeypatch, tmp_path):
    """每个测试用独立临时库，避免相互污染。"""
    dbp = str(tmp_path / "emp.db")
    monkeypatch.setattr(_cfg, "DB_PATH", dbp)
    monkeypatch.setattr(_base, "DB_PATH", dbp)
    db.init_config_db()
    return dbp


def _set_email(emp_id="emp-009", addr="b4@163.com", pwd="SECRETCODE"):
    db.db_set_employee_channel(emp_id, "email", True, {
        "address": addr, "password": pwd,
        "smtp_host": "smtp.163.com", "smtp_port": 465,
        "imap_host": "imap.163.com", "imap_port": 993,
        "display_name": "采购智能体",
    })


def test_employee_channel_crud(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    db.db_upsert_employee({"id": "emp-009", "name": "t", "type": "采购询比价(本体)"})
    assert db.db_set_employee_channel("emp-009", "email", True,
                                      {"address": "b4@163.com", "password": "X"})
    ch = db.db_get_employee_channel("emp-009", "email")
    assert ch["config"]["address"] == "b4@163.com"
    assert ch["config"]["password"] == "X"
    assert ch["enabled"] is True
    lst = db.db_list_employee_channels("emp-009")
    assert any(c["channel"] == "email" for c in lst)
    # 缺失返回 None
    assert db.db_get_employee_channel("emp-009", "feishu") is None


def test_channels_api_mask_and_preserve(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    db.db_upsert_employee({"id": "emp-009", "name": "t", "type": "采购询比价(本体)"})
    _set_email()

    r = client.get("/api/employees/emp-009/channels")
    assert r.status_code == 200
    ch = next(c for c in r.json()["channels"] if c["channel"] == "email")
    assert ch["config"]["address"] == "b4@163.com"
    assert ch["config"]["password"] != "SECRETCODE"   # 掩码
    assert "****" in ch["config"]["password"]

    # 空密码保存 → 保留原密码（避免误清空导致发信失败）
    r2 = client.put("/api/employees/emp-009/channels/email", json={"enabled": True, "config": {
        "address": "b4@163.com", "password": "",
        "smtp_host": "smtp.163.com", "smtp_port": 465,
        "imap_host": "imap.163.com", "imap_port": 993, "display_name": "采购智能体"}})
    assert r2.status_code == 200
    ch2 = db.db_get_employee_channel("emp-009", "email")
    assert ch2["config"]["password"] == "SECRETCODE"

    # 启用但缺 address/password → 拒绝
    r3 = client.put("/api/employees/emp-009/channels/email", json={"enabled": True, "config": {
        "address": "", "password": "", "smtp_host": "smtp.163.com", "smtp_port": 465,
        "imap_host": "imap.163.com", "imap_port": 993, "display_name": "x"}})
    assert r3.status_code == 400


def test_employee_enabled_gate(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    from app.ontology.registration import register_emp009
    register_emp009()
    from app.ontology import execution
    execution.set_governor(mode="ontology", exec_enabled=True)

    # 默认注册即启用
    assert execution._employee_managed() is True
    assert execution.needs_exec() is True

    # 停用员工 → 运行时停止
    db.db_set_employee_enabled("emp-009", False)
    assert execution._employee_managed() is False
    assert execution.needs_exec() is False

    # 重新启用
    db.db_set_employee_enabled("emp-009", True)
    assert execution.needs_exec() is True

    # 关联技能停用 → 同样停止
    db.db_set_employee_skill_enabled("emp-009", "skill-ont-proc-inquiry", False)
    assert execution._employee_managed() is False
    db.db_set_employee_skill_enabled("emp-009", "skill-ont-proc-inquiry", True)
    assert execution._employee_managed() is True


def test_employee_unknown_backward_compat(tmp_path, monkeypatch):
    """未注册员工（旧库/测试库）时按历史默认放行，避免误伤现有测试。"""
    _fresh(monkeypatch, tmp_path)
    from app.ontology import execution
    execution.set_governor(mode="ontology", exec_enabled=True)
    # 库里没有 emp-009 → 视为已启用
    assert execution._employee_managed() is True
    assert execution.needs_exec() is True


def test_mail_gateway_reads_employee_channel(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    db.db_upsert_employee({"id": "emp-009", "name": "t", "type": "采购询比价(本体)"})
    _set_email(addr="b4chan@163.com", pwd="CHANPWD")
    from app.ontology.mail_gateway import _ont_mail_cfg
    cfg = _ont_mail_cfg("emp-009")
    assert cfg["mail_username"] == "b4chan@163.com"
    assert cfg["mail_password"] == "CHANPWD"
    assert cfg["smtp_host"] == "smtp.163.com"
