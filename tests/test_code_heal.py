# -*- coding: utf-8 -*-
"""代码级自愈测试：护栏（白名单/补丁校验）、规则修复器、全流程（修复→测试→发布→验证→回滚）"""
import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app import ops_code_heal as heal  # noqa: E402


def _make_repo(tmpdir):
    """构造最小仓库：app/db.py（含目标连接代码）+ requirements.txt"""
    appdir = os.path.join(tmpdir, "app")
    os.makedirs(appdir, exist_ok=True)
    with open(os.path.join(appdir, "db.py"), "w", encoding="utf-8") as f:
        f.write('conn = sqlite3.connect(DB_PATH, check_same_thread=False)\n')
    with open(os.path.join(tmpdir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("fastapi\nuvicorn\n")
    return appdir


def test_allowed_target_whitelist():
    """护栏：仅允许白名单前缀内文件"""
    assert heal._allowed_target("app/db.py", "/repo")
    assert heal._allowed_target("requirements.txt", "/repo")
    assert heal._allowed_target("tests/test_x.py", "/repo")
    assert not heal._allowed_target("../evil.py", "/repo")
    assert not heal._allowed_target("/etc/passwd", "/repo")
    assert not heal._allowed_target("scripts/../etc/passwd", "/repo")


def test_validate_patch():
    """补丁校验：old 必须真实存在、new 非空"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_repo(tmp)
        ok, info = heal._validate_patch(
            {"target": "app/db.py", "old": "conn = sqlite3.connect(DB_PATH, check_same_thread=False)",
             "new": "conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)"}, tmp)
        assert ok, info
        # old 不存在 → 拦截
        ok2, info2 = heal._validate_patch(
            {"target": "app/db.py", "old": "nonexistent code", "new": "x"}, tmp)
        assert not ok2
        # 白名单外 → 拦截
        ok3, info3 = heal._validate_patch(
            {"target": "data/secret.txt", "old": "a", "new": "b"}, tmp)
        assert not ok3


def test_sqlite_locked_fixer():
    """规则修复器：database is locked → busy timeout + WAL 补丁"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_repo(tmp)
        patch = heal._sqlite_locked_fixer("OperationalError: database is locked", tmp)
        assert patch and patch["target"] == "app/db.py"
        assert "timeout=30" in patch["new"]
        # 非匹配上下文 → None
        assert heal._sqlite_locked_fixer("normal log", tmp) is None


def test_missing_module_fixer():
    """规则修复器：No module named → requirements.txt 追加"""
    with tempfile.TemporaryDirectory() as tmp:
        _make_repo(tmp)
        patch = heal._missing_module_fixer("ModuleNotFoundError: No module named 'psutil'", tmp)
        assert patch and patch["target"] == "requirements.txt"
        assert "psutil" in patch["new"]
        # 已声明 → None
        with open(os.path.join(tmp, "requirements.txt"), "a") as f:
            f.write("psutil\n")
        assert heal._missing_module_fixer("No module named 'psutil'", tmp) is None


def test_run_code_heal_full_flow_recovered():
    """全流程：检测→修复→测试→发布→验证→recovered"""
    db.init_ops_db()
    db.db_set_setting("code_heal_enabled", "1")
    db.db_set_setting("self_heal_enabled", "1")
    with tempfile.TemporaryDirectory() as tmp:
        _make_repo(tmp)
        db.db_set_setting("app_code_repo", tmp)
        iid = "INC-HEAL-" + os.urandom(4).hex().upper()
        db.incident_create(iid, 1, "应用日志错误突增", "log", "统一日志",
                           "warning", "OperationalError: database is locked", "2026-08-15 10:00:00")
        # 写入错误日志上下文
        db.ops_save_logs([("2026-08-15 10:00:00", "app:neuops", "error",
                           "OperationalError: database is locked")])
        with mock.patch.object(heal, "_run_tests_for_patch", return_value=(True, "ok")), \
             mock.patch.object(heal, "_restart_9007", return_value=True), \
             mock.patch.object(heal, "_verify_healthy", return_value=True), \
             mock.patch.object(heal, "_is_git_repo", return_value=False):
            inc = heal.run_code_heal(iid)
        assert inc["state"] == "recovered", inc.get("fix_log")
        # 补丁真实应用：db.py 已包含 timeout
        with open(os.path.join(tmp, "app", "db.py")) as f:
            assert "timeout=30" in f.read()
        with db._db_lock:
            conn = db._get_conn()
            try:
                conn.execute("DELETE FROM incidents WHERE id=?", (iid,))
                conn.execute("DELETE FROM ops_logs WHERE source='app:neuops'")
                conn.commit()
            finally:
                conn.close()


def test_run_code_heal_verify_fail_rollback():
    """验证失败 → 自动回滚 + manual"""
    db.init_ops_db()
    db.db_set_setting("code_heal_enabled", "1")
    db.db_set_setting("self_heal_enabled", "1")
    with tempfile.TemporaryDirectory() as tmp:
        _make_repo(tmp)
        db.db_set_setting("app_code_repo", tmp)
        iid = "INC-HEAL2-" + os.urandom(4).hex().upper()
        db.incident_create(iid, 1, "应用日志错误突增", "log", "统一日志",
                           "warning", "OperationalError: database is locked", "2026-08-15 10:00:00")
        db.ops_save_logs([("2026-08-15 10:00:01", "app:neuops", "error",
                           "OperationalError: database is locked")])
        with mock.patch.object(heal, "_run_tests_for_patch", return_value=(True, "ok")), \
             mock.patch.object(heal, "_restart_9007", return_value=True), \
             mock.patch.object(heal, "_verify_healthy", return_value=False), \
             mock.patch.object(heal, "_is_git_repo", return_value=False):
            inc = heal.run_code_heal(iid)
        assert inc["state"] == "manual"
        # 文件已回滚到原样
        with open(os.path.join(tmp, "app", "db.py")) as f:
            assert "timeout=30" not in f.read()
        with db._db_lock:
            conn = db._get_conn()
            try:
                conn.execute("DELETE FROM incidents WHERE id=?", (iid,))
                conn.execute("DELETE FROM ops_logs WHERE source='app:neuops'")
                conn.commit()
            finally:
                conn.close()


def test_run_code_heal_no_context_manual():
    """无错误上下文 → 护栏拦截升级人工"""
    db.init_ops_db()
    iid = "INC-HEAL3-" + os.urandom(4).hex().upper()
    db.incident_create(iid, 1, "应用日志错误突增", "log", "统一日志",
                       "warning", "", "2026-08-15 10:00:00")
    inc = heal.run_code_heal(iid)
    assert inc["state"] == "manual"
    with db._db_lock:
        conn = db._get_conn()
        try:
            conn.execute("DELETE FROM incidents WHERE id=?", (iid,))
            conn.commit()
        finally:
            conn.close()


def test_run_code_heal_disabled_manual():
    """代码自愈开关关闭 → 升级人工"""
    db.init_ops_db()
    db.db_set_setting("code_heal_enabled", "0")
    iid = "INC-HEAL4-" + os.urandom(4).hex().upper()
    db.incident_create(iid, 1, "应用日志错误突增", "log", "统一日志",
                       "warning", "some error", "2026-08-15 10:00:00")
    inc = heal.run_code_heal(iid)
    assert inc["state"] == "manual"
    db.db_set_setting("code_heal_enabled", "1")
    with db._db_lock:
        conn = db._get_conn()
        try:
            conn.execute("DELETE FROM incidents WHERE id=?", (iid,))
            conn.commit()
        finally:
            conn.close()
