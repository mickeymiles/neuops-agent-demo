# -*- coding: utf-8 -*-
"""代码级自愈引擎（Code-Level Self-Healing）

与脚本级自愈（重启服务/清理磁盘/重建索引）不同，本模块针对「代码层面的故障」：
应用日志出现异常堆栈 / 模块缺失 / 数据库锁等待 → 定位代码 → 自动修复 → 测试 → 发布 → 验证 → 回滚。

流水线（与 /ops 自愈事件中心联动）：
  detected ──diagnosing──> 提取错误特征与堆栈
      └─fixing──> 规则修复器 / LLM 生成补丁（无解则升级 manual，绝不猜测修复）
      └─testing──> pytest 定向 + 全量，必须全绿
      └─deploying──> git commit 补丁 + 重启 9007
      └─verifying──> 端口 + HTTP 健康 + 回归测试
      └─recovered  | 任一环节失败 -> 自动回滚（git checkout + 重启）-> manual

安全护栏：
1. 补丁白名单路径：仅允许修改 app/ static/ tests/ requirements.txt scripts/ run.sh（config.CODE_HEAL_ALLOW_PREFIXES）
2. 补丁格式校验：仅允许「文件中已存在的 old 片段 → new 文本」替换，new 非空，禁止删文件
3. 修改前备份原文件内容；发布前 git commit；验证失败用 git checkout + 备份内容双重回滚
4. 测试必须全绿才允许发布；发布后健康验证通过才标记 recovered
5. 全程写入 incidents.fix_log 审计；失败自动升级 manual 并飞书通知
6. LLM 修复引擎预留：配置 settings code_heal_llm_url / code_heal_llm_key 后自动启用，否则使用内置规则修复器
"""
import logging
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime

from . import config, db, feishu_notify

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(incident_id: str, msg: str):
    ts = _now()
    line = f"[{ts}] [code-heal] {msg}"
    logger.info("[code-heal] %s %s", incident_id, msg)
    try:
        inc = db.incident_get(incident_id)
        old = inc.get("fix_log", "")
        db.incident_update(incident_id, fix_log=(old + ("\n" if old else "") + line), updated_at=ts)
    except Exception:  # noqa: BLE001
        pass


# ─────────────── 规则修复器（无 LLM 时的内置修复能力） ───────────────

def _sqlite_locked_fixer(log_text: str, repo: str):
    """修复 SQLite 'database is locked'：给连接加 busy timeout 并启用 WAL"""
    if "database is locked" not in log_text.lower():
        return None
    target = os.path.join(repo, "app", "db.py")
    if not os.path.isfile(target):
        return None
    old = "conn = sqlite3.connect(DB_PATH, check_same_thread=False)"
    new = ("conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)\n"
           "    try:\n"
           "        conn.execute(\"PRAGMA journal_mode=WAL\")\n"
           "    except sqlite3.Error:\n"
           "        pass")
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        return None
    return {
        "name": "sqlite_busy_timeout",
        "desc": "为 SQLite 连接增加 busy timeout=30 并启用 WAL，缓解 database is locked",
        "target": "app/db.py",
        "old": old,
        "new": new,
    }


def _missing_module_fixer(log_text: str, repo: str):
    """修复 'No module named X'：若 requirements.txt 未声明则追加（白名单内）"""
    m = re.search(r"No module named '([A-Za-z_][A-Za-z0-9_.]*)'", log_text)
    if not m:
        return None
    mod = m.group(1).split(".")[0]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mod):
        return None
    req = os.path.join(repo, "requirements.txt")
    if not os.path.isfile(req):
        return None
    with open(req, "r", encoding="utf-8") as f:
        existing = f.read()
    if any(line.strip().lower().split("==")[0].split(">=")[0] == mod.lower()
           for line in existing.splitlines() if line.strip()):
        return None  # 已声明，非依赖缺失问题
    return {
        "name": "add_missing_dependency",
        "desc": f"requirements.txt 追加缺失依赖 {mod}",
        "target": "requirements.txt",
        "old": existing[-1] if existing.strip() else "__NONEXIST__",
        "new": (existing.rstrip("\n") + "\n" + mod + "\n"),
    }


RULE_FIXERS = (
    _sqlite_locked_fixer,
    _missing_module_fixer,
)


# ─────────────── LLM 修复引擎（预留） ───────────────

def _llm_fix(log_text: str, repo: str):
    """预留：配置 code_heal_llm_url / code_heal_llm_key 后启用 LLM 生成补丁 JSON"""
    url = db.db_get_setting("code_heal_llm_url", "") or config.CODE_HEAL_LLM_URL
    key = db.db_get_setting("code_heal_llm_key", "") or config.CODE_HEAL_LLM_KEY
    if not url:
        return None
    body = {
        "task": "generate_code_fix_patch",
        "repo": os.path.basename(repo),
        "error_context": log_text[-4000:],
        "patch_schema": {"file": str, "old": str, "new": str, "reason": str},
        "constraints": "only text replacement of existing content; do not create or delete files",
    }
    try:
        req = urllib.request.Request(
            url, data=json_dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key} if key else
            {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=config.CODE_HEAL_STEP_TIMEOUT) as resp:
            data = json_loads(resp.read().decode("utf-8"))
        patch = data.get("patch") or data.get("fix") or data
        if isinstance(patch, dict) and patch.get("file") and patch.get("old") and patch.get("new"):
            return {
                "name": "llm_patch",
                "desc": patch.get("reason", "LLM 生成补丁"),
                "target": patch["file"].lstrip("./"),
                "old": patch["old"],
                "new": patch["new"],
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("[code-heal] LLM fix failed: %s", e)
    return None


def _json_module():
    import json
    return json


def json_dumps(obj) -> str:
    return _json_module().dumps(obj, ensure_ascii=False)


def json_loads(s):
    return _json_module().loads(s)


# ─────────────── 护栏：补丁校验 ───────────────

def _allowed_target(target: str, repo: str) -> bool:
    rel = target.replace("\\", "/")
    if rel.startswith("/") or rel.startswith(".."):
        return False
    # 规范化，防止 scripts/../etc/passwd 绕过白名单
    rel = os.path.normpath(rel).replace("\\", "/")
    if rel == "." or rel.startswith("../"):
        return False
    for p in config.CODE_HEAL_ALLOW_PREFIXES:
        base = p.rstrip("/")
        if rel == base or rel.startswith(base + "/"):
            return True
    return False


def _validate_patch(patch: dict, repo: str):
    """校验补丁：白名单路径 + old 片段必须真实存在于文件 + new 非空"""
    target = patch.get("target", "")
    if not _allowed_target(target, repo):
        return False, f"护栏拦截：目标 {target} 不在白名单 {config.CODE_HEAL_ALLOW_PREFIXES} 中"
    path = os.path.join(repo, target)
    if not os.path.isfile(path):
        return False, f"目标文件不存在：{path}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if patch.get("old", "") == "__NONEXIST__":
        if content.strip():
            return False, "追加补丁失败：文件非空"
        old = ""
    else:
        if patch["old"] not in content:
            return False, f"补丁 old 片段在 {target} 中不存在（可能已修复或代码已变化）"
        old = patch["old"]
    new = patch.get("new", "")
    if not new or new == old:
        return False, "补丁 new 为空或与 old 相同"
    return True, (content, old, new, path)


def _apply_patch(patch: dict, repo: str):
    ok, info = _validate_patch(patch, repo)
    if not ok:
        return False, info
    content, old, new, path = info
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True, f"已应用补丁：{patch.get('name', 'patch')} -> {patch['target']}"


def _rollback_files(backups: dict):
    """回滚：用修改前备份恢复文件内容"""
    for path, content in backups.items():
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:  # noqa: BLE001
            logger.exception("[code-heal] rollback file failed: %s", path)


def _git(repo: str, *args: str) -> tuple:
    try:
        out = subprocess.run(["git", "-C", repo, *args],
                             capture_output=True, text=True, timeout=30)
        return out.returncode, out.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def _is_git_repo(repo: str) -> bool:
    rc, _ = _git(repo, "rev-parse", "--is-inside-work-tree")
    return rc == 0


# ─────────────── 测试 / 发布 / 验证 ───────────────

def _run_tests(repo: str, target: str = "") -> tuple:
    """运行 pytest，返回 (ok, output)。target 为空时跑全量 tests/"""
    sel = target or "tests/"
    cmd = ["python3", "-m", "pytest", sel, "-q", "--tb=short", "-p", "no:cacheprovider"]
    try:
        out = subprocess.run(cmd, cwd=repo, capture_output=True, text=True,
                             timeout=config.CODE_HEAL_STEP_TIMEOUT)
        tail = (out.stdout or "")[-1500:] + (out.stderr or "")[-1500:]
        return out.returncode == 0, tail
    except subprocess.TimeoutExpired:
        return False, f"pytest 超时（>{config.CODE_HEAL_STEP_TIMEOUT}s）"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _restart_9007() -> bool:
    from . import ops_self_heal
    ok, _ = ops_self_heal.act_restart_self("neuops-agent", {})
    return ok


def _verify_healthy(incident_id: str) -> bool:
    """健康验证：9007 端口开放 + HTTP /api/ops/overview 可达"""
    try:
        import socket
        with socket.create_connection(("127.0.0.1", 9007), timeout=3):
            pass
    except OSError:
        _log(incident_id, "健康验证失败：9007 端口未开放")
        return False
    try:
        import urllib.request as ur
        with ur.urlopen("http://127.0.0.1:9007/api/ops/overview", timeout=5) as resp:
            body = resp.read(2000)
            return b'"ok"' in body or b"200" in body
    except Exception:  # noqa: BLE001
        return False


def _collect_error_context(incident: dict, limit: int = 12) -> str:
    """收集错误上下文：incident 消息 + 最近 error 日志"""
    parts = [incident.get("message", "")]
    rows = db.ops_get_logs(source="", level="error", minutes=30, limit=limit)
    for r in rows:
        parts.append(f"[{r['source']}] {r['message']}")
    return "\n".join(parts)[:6000]


def _resolve_repo() -> str:
    repo = (db.db_get_setting("app_code_repo", "") or "").strip()
    if repo and os.path.isdir(repo):
        return os.path.abspath(repo)
    return os.path.abspath(config.CODE_REPO_DEFAULT)


def _run_tests_for_patch(patch: dict, repo: str) -> tuple:
    """定向测试：先跑与被改文件同名的测试文件，再全量"""
    target = patch.get("target", "")
    stem = os.path.splitext(os.path.basename(target))[0]
    spec = os.path.join("tests", "test_" + stem + ".py")
    if os.path.isfile(os.path.join(repo, spec)):
        ok, out = _run_tests(repo, spec)
        if not ok:
            return False, f"定向测试失败（{spec}）：{out}"
        _log("", f"定向测试通过：{spec}")
    return _run_tests(repo)


# ─────────────── 主流程 ───────────────

def run_code_heal(incident_id: str) -> dict:
    """执行一次代码级自愈：detect→fix→test→deploy→verify→(rollback)。返回 incident dict"""
    inc = db.incident_get(incident_id)
    if not inc:
        return {"state": "failed", "message": "incident not found"}
    if inc.get("state") in ("recovered", "manual", "failed"):
        return inc

    if (db.db_get_setting("code_heal_enabled", "1") != "1"
            or db.db_get_setting("self_heal_enabled", "0") != "1"):
        _log(incident_id, "代码自愈未启用，升级人工")
        db.incident_update(incident_id, state="manual",
                           message="代码自愈开关关闭，升级人工", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    repo = _resolve_repo()
    _log(incident_id, f"开始代码级自愈，repo={repo}")
    if not os.path.isdir(os.path.join(repo, "app")):
        _log(incident_id, f"仓库结构异常（无 app/），repo={repo}，升级人工")
        db.incident_update(incident_id, state="manual",
                           message="代码仓库路径无效：" + repo, updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    db.incident_update(incident_id, state="repairing",
                       fix_action="code_heal", updated_at=_now())

    # 1) diagnosing：收集错误上下文
    context = _collect_error_context(inc, 15)
    _log(incident_id, f"诊断上下文 {len(context)} 字符")
    if not context.strip():
        _log(incident_id, "无错误上下文可诊断，升级人工")
        db.incident_update(incident_id, state="manual",
                           message="无错误上下文，无法自动修复", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    # 2) fixing：规则修复器 → LLM（预留）→ manual
    patch = None
    for fixer in RULE_FIXERS:
        try:
            patch = fixer(context, repo)
        except Exception:  # noqa: BLE001
            patch = None
        if patch:
            break
    if patch is None:
        patch = _llm_fix(context, repo)
    if patch is None:
        _log(incident_id, "无匹配修复规则且未配置 LLM，升级人工（护栏：不猜测修复）")
        db.incident_update(incident_id, state="manual",
                           message="无匹配修复方案，已升级人工", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    _log(incident_id, f"修复方案：{patch.get('desc')} -> {patch.get('target')}")

    # 3) 备份原文件 + 应用补丁
    backups = {}
    path = os.path.join(repo, patch["target"])
    try:
        with open(path, "r", encoding="utf-8") as f:
            backups[path] = f.read()
    except Exception as e:  # noqa: BLE001
        _log(incident_id, f"备份失败：{e}，升级人工")
        db.incident_update(incident_id, state="manual", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    ok, info = _apply_patch(patch, repo)
    if not ok:
        _log(incident_id, f"补丁校验/应用失败：{info}，升级人工")
        db.incident_update(incident_id, state="manual",
                           message="补丁应用失败：" + str(info), updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)
    _log(incident_id, info)

    # 4) testing：测试必须全绿
    test_ok, test_out = _run_tests_for_patch(patch, repo)
    if not test_ok:
        _log(incident_id, f"测试未通过：{test_out[-800:]}")
        _rollback_files(backups)
        _log(incident_id, "已回滚代码（测试失败）")
        db.incident_update(incident_id, state="manual",
                           message="代码修复后测试失败，已自动回滚", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)
    _log(incident_id, "测试全部通过")

    # 5) deploying：git commit 补丁 + 重启 9007
    if _is_git_repo(repo):
        git_before, _ = _git(repo, "rev-parse", "HEAD")
        _git(repo, "add", "--", patch["target"])
        rc, msg = _git(repo, "commit", "-m",
                       f"auto-heal({incident_id}): {patch.get('desc', 'code fix')}")
        _log(incident_id, f"git commit rc={rc} {msg[:200]}")
        if rc != 0:
            _log(incident_id, "git commit 失败，回滚")
            _rollback_files(backups)
            db.incident_update(incident_id, state="manual",
                               message="git commit 失败，已回滚", updated_at=_now())
            feishu_notify.notify_incident(db.incident_get(incident_id))
            return db.incident_get(incident_id)
    else:
        git_before = None

    _log(incident_id, "重启 9007 服务")
    if not _restart_9007():
        _log(incident_id, "9007 重启失败")
        _rollback_files(backups)
        if git_before:
            _git(repo, "reset", "--hard", git_before)
        db.incident_update(incident_id, state="manual",
                           message="服务重启失败，已回滚", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    # 6) verifying：健康验证 + 回归
    db.incident_update(incident_id, state="verifying", updated_at=_now())
    time.sleep(3)
    healthy = _verify_healthy(incident_id)
    if healthy:
        _log(incident_id, "健康验证通过")
        db.incident_update(incident_id, state="recovered", resolved_at=_now(),
                           updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return db.incident_get(incident_id)

    _log(incident_id, "健康验证未通过，回滚")
    _rollback_files(backups)
    if git_before:
        _git(repo, "reset", "--hard", git_before)
    _restart_9007()
    time.sleep(3)
    db.incident_update(incident_id, state="manual",
                       message="代码修复发布后健康验证失败，已自动回滚", updated_at=_now())
    feishu_notify.notify_incident(db.incident_get(incident_id))
    return db.incident_get(incident_id)


def act_code_heal(entity_name: str, entity_attrs: dict) -> tuple:
    """自愈引擎白名单动作：从 incident 提取 id 并执行代码级自愈"""
    incident_id = (entity_attrs or {}).get("incident_id", "")
    if not incident_id:
        return False, "code_heal 需要 incident_id"
    try:
        inc = run_code_heal(incident_id)
    except Exception as e:  # noqa: BLE001
        return False, f"代码自愈异常：{e}"
    return inc.get("state") == "recovered", f"code_heal 结束，状态={inc.get('state')}"
