# -*- coding: utf-8 -*-
"""自愈状态机测试：检测→修复→验证→恢复 / 失败升级"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.ops_self_heal import (  # noqa: E402
    HEAL_ACTIONS,
    _choose_action,
    create_incident_from_alert,
)


def test_heal_actions_whitelist():
    """护栏：动作白名单固定（含代码级自愈 code_heal）"""
    assert set(HEAL_ACTIONS.keys()) == {
        "restart_service", "restart_9006", "recycle_container",
        "cleanup_disk", "restore_db", "restart_self", "code_heal",
    }


def test_choose_action_code_heal():
    """日志/代码类故障应路由到代码级自愈"""
    assert _choose_action({"entity_type": "log", "entity_name": "统一日志",
                           "rule_name": "应用日志错误突增"}) == "code_heal"
    assert _choose_action({"entity_type": "log", "entity_name": "统一日志",
                           "rule_name": "rule-ops-007"}) == "code_heal"


def test_choose_action():
    """按实体类型选择白名单动作"""
    assert _choose_action({"entity_type": "application", "entity_name": "contract-compare",
                           "rule_name": "应用健康检查失败"}) == "restart_9006"
    assert _choose_action({"entity_type": "application", "entity_name": "neuops-agent",
                           "rule_name": "应用健康检查失败"}) == "restart_self"
    assert _choose_action({"entity_type": "container", "entity_name": "web",
                           "rule_name": "x"}) == "recycle_container"
    assert _choose_action({"entity_type": "database", "entity_name": "db",
                           "rule_name": "x"}) == "restore_db"
    assert _choose_action({"entity_type": "server", "entity_name": "srv",
                           "rule_name": "disk_percent"}) == "cleanup_disk"


def test_create_incident_and_dedup():
    db.init_ops_db()
    rid = "rule-test-" + uuid.uuid4().hex[:6]
    inc1 = create_incident_from_alert(999999, "测试规则", "application", "test-app",
                                      "critical", "测试故障")
    # 同告警再次创建应返回同一事件
    inc2 = create_incident_from_alert(999999, "测试规则", "application", "test-app",
                                      "critical", "测试故障")
    assert inc1["id"] == inc2["id"]
    assert inc1["state"] in ("detected", "repairing", "verifying", "recovered", "failed", "manual")
    # 清理
    db._get_conn().execute("DELETE FROM incidents WHERE id=?", (inc1["id"],)).connection.commit()


def test_incident_state_machine():
    """状态机：detected → repairing → verifying → recovered/failed/manual"""
    db.init_ops_db()
    iid = "INC-TEST-" + uuid.uuid4().hex[:6]
    db.incident_create(iid, 0, "t", "server", "srv", "warning", "m", "2026-08-15 00:00:00")
    inc = db.incident_get(iid)
    assert inc["state"] == "detected"
    db.incident_update(iid, state="repairing")
    assert db.incident_get(iid)["state"] == "repairing"
    db.incident_update(iid, state="verifying")
    assert db.incident_get(iid)["state"] == "verifying"
    db.incident_update(iid, state="recovered", resolved_at="2026-08-15 00:01:00")
    assert db.incident_get(iid)["state"] == "recovered"
    db._get_conn().execute("DELETE FROM incidents WHERE id=?", (iid,)).connection.commit()
