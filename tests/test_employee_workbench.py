# -*- coding: utf-8 -*-
"""数字员工工作台测试。# 规格编号: NO-009 FR-1 / FR-2"""

from fastapi.testclient import TestClient

import app.db as db
from main import app

client = TestClient(app)


def _seed_employee(emp_id: str, name: str, emp_type: str):
    db.db_upsert_employee({"id": emp_id, "name": name, "type": emp_type})


def test_employee_types_receive_different_default_workbenches(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workbench.db"))
    db.init_config_db()
    _seed_employee("emp-business", "经营专家", "经营分析")
    _seed_employee("emp-alert", "告警专家", "告警根因")

    business = client.get("/api/employees/emp-business/full").json()
    alert = client.get("/api/employees/emp-alert/full").json()

    assert business["workbench_custom"] is False
    business_components = business["workbench"]["components"]
    alert_components = alert["workbench"]["components"]
    business_metrics = next(c for c in business_components if c["type"] == "metric")
    alert_metrics = next(c for c in alert_components if c["type"] == "metric")
    assert business_metrics["items"] != alert_metrics["items"]
    assert any(c["type"] == "business_app" for c in business_components)
    assert not any(c["type"] == "business_app" for c in alert_components)


def test_workbench_can_be_saved_and_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workbench.db"))
    db.init_config_db()
    _seed_employee("emp-custom", "定制员工", "通用")
    custom = {
        "title": "专属工作台",
        "description": "按员工隔离",
        "components": [{
            "id": "notice",
            "type": "note",
            "title": "说明",
            "content": "这是定制内容",
        }],
    }

    saved = client.patch("/api/employees/emp-custom", json={"workbench": custom})
    assert saved.status_code == 200
    detail = client.get("/api/employees/emp-custom/full").json()
    assert detail["workbench_custom"] is True
    assert detail["workbench"] == custom

    restored = client.patch("/api/employees/emp-custom", json={"workbench": None})
    assert restored.status_code == 200
    detail = client.get("/api/employees/emp-custom/full").json()
    assert detail["workbench_custom"] is False
    assert detail["workbench"]["title"] == "定制员工工作台"


def test_invalid_workbench_is_rejected_without_overwriting_config(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workbench.db"))
    db.init_config_db()
    _seed_employee("emp-guarded", "受保护员工", "通用")
    valid = {
        "title": "原工作台",
        "components": [{"id": "note", "type": "note", "title": "说明", "content": "保留"}],
    }
    assert client.patch("/api/employees/emp-guarded", json={"workbench": valid}).status_code == 200

    invalid = {"title": "危险配置", "components": [{"id": "run", "type": "script", "items": []}]}
    response = client.patch("/api/employees/emp-guarded", json={"workbench": invalid})

    assert response.status_code == 400
    assert client.get("/api/employees/emp-guarded/full").json()["workbench"] == valid


def test_business_app_rejects_custom_url(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workbench.db"))
    db.init_config_db()
    _seed_employee("emp-guarded", "受保护员工", "经营分析")
    workbench = {
        "title": "危险嵌入",
        "components": [{
            "id": "external",
            "type": "business_app",
            "title": "外部系统",
            "content": "https://example.com",
        }],
    }

    response = client.patch("/api/employees/emp-guarded", json={"workbench": workbench})

    assert response.status_code == 400


def test_seed_sync_preserves_custom_workbench(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workbench.db"))
    db.init_config_db()
    seed_employee = db.MOCK_EMPLOYEES[0]
    custom = {
        "title": "重启后保留",
        "components": [{"id": "note", "type": "note", "title": "说明", "content": "持久化"}],
    }
    db.db_upsert_employee({**seed_employee, "workbench": custom})

    db.sync_seed_employees()

    assert db.db_get_employee(seed_employee["id"])["workbench"] == custom