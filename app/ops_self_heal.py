# -*- coding: utf-8 -*-
"""全自动自愈引擎

流程：
  detected → repairing → verifying → recovered
                 ↗ 失败且重试<上限
                 ↓ 重试>=上限
               failed → manual

安全护栏：
1. 修复动作白名单：仅允许预定义动作（restart_service / recycle_container / cleanup_disk / restore_db / restart_9006）。
2. 单事件最大重试 2 次（页面可配）。
3. 修复后必须健康验证通过才标记 recovered；任何失败记录修复日志。
4. 失败升级飞书人工通知。
5. 所有动作写入 incidents 审计日志。
"""
import logging
import os
import socket
import subprocess
import threading
import time
import uuid
from datetime import datetime

from . import db, feishu_notify

logger = logging.getLogger(__name__)

INCIDENT_STATES = ("detected", "repairing", "verifying", "recovered", "failed", "manual")

# 白名单修复动作 → 函数名。禁止任何不在此映射中的动作。
HEAL_ACTIONS = {
    "restart_service": "act_restart_service",
    "restart_9006": "act_restart_9006",
    "recycle_container": "act_recycle_container",
    "cleanup_disk": "act_cleanup_disk",
    "restore_db": "act_restore_db",
    "restart_self": "act_restart_self",
    "code_heal": "act_code_heal",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_enabled() -> bool:
    return db.db_get_setting("self_heal_enabled", "0") == "1"


def _max_retry() -> int:
    try:
        return max(0, int(db.db_get_setting("self_heal_max_retry", "2")))
    except ValueError:
        return 2


def _log(incident_id: str, msg: str):
    ts = _now()
    line = f"[{ts}] {msg}"
    logger.info("[self-heal] %s %s", incident_id, msg)
    try:
        inc = db.incident_get(incident_id)
        old = inc.get("fix_log", "")
        db.incident_update(incident_id, fix_log=(old + ("\n" if old else "") + line), updated_at=ts)
    except Exception:  # noqa: BLE001
        pass


# ─────────────── 修复动作实现（白名单） ───────────────

def act_restart_service(entity_name: str, entity_attrs: dict) -> tuple:
    """重启一个 systemd 服务或 supervisor 进程；entity_attrs 中可有 unit_name"""
    unit = entity_attrs.get("unit_name", entity_name)
    # 仅允许明确以 .service 或已知服务名结尾
    safe_names = ("neuops", "contract-compare", "nginx", "redis", "mysql", "postgresql")
    if not any(unit.lower().startswith(s) or unit.lower().endswith(".service") for s in safe_names):
        return False, f"refused to restart unsafe service: {unit}"
    try:
        out = subprocess.run(["sudo", "systemctl", "restart", unit],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return True, "systemctl restart " + unit
        # 尝试 supervisorctl
        out2 = subprocess.run(["sudo", "supervisorctl", "restart", unit],
                              capture_output=True, text=True, timeout=30)
        if out2.returncode == 0:
            return True, "supervisorctl restart " + unit
        return False, out.stderr or out2.stderr or "restart failed"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _listening_info(port: int) -> dict:
    """返回监听指定端口的进程信息：{cmd, cwd, pids}（仅本机）"""
    try:
        out = subprocess.run(["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=10)
        pids = [p for p in out.stdout.split() if p.isdigit()]
        if not pids:
            return {"cmd": "", "cwd": "", "pids": []}
        ps = subprocess.run(["ps", "-p", ",".join(pids), "-o", "args="],
                            capture_output=True, text=True, timeout=10)
        cwd = ""
        try:
            c = subprocess.run(["lsof", "-a", "-p", pids[0], "-d", "cwd", "-Fn"],
                               capture_output=True, text=True, timeout=10)
            for line in c.stdout.splitlines():
                if line.startswith("n/"):
                    cwd = line[2:]
                    break
        except Exception:  # noqa: BLE001
            pass
        return {"cmd": ps.stdout.strip(), "cwd": cwd, "pids": pids}
    except Exception:  # noqa: BLE001
        return {"cmd": "", "cwd": "", "pids": []}


def act_restart_9006(_entity_name: str, _entity_attrs: dict) -> tuple:
    """重启 9006 服务：优先 contract-compare 项目，回退到本机 app.server 模拟服务（精确匹配，避免误杀）"""
    root = os.environ.get("APP_9006_ROOT", "/home/ubuntu/contract-compare")
    # 9006 工作目录：优先 settings 配置 → 环境变量 → 探测监听进程 cwd
    cwd = db.db_get_setting("app_9006_cwd", "").strip() or os.environ.get("APP_9006_CWD", "")
    try:
        listening = _listening_info(9006)
        # 情况1：本机 app.server 模拟服务（python -m app.server 9006）→ 从进程 cwd 重启
        if "app.server" in listening["cmd"] and "9006" in listening["cmd"]:
            cwd = cwd or listening["cwd"] or os.getcwd()
            try:
                subprocess.run(["pkill", "-f", r"app\.server 9006"], capture_output=True,
                               text=True, timeout=10)
                time.sleep(1)
            except Exception:  # noqa: BLE001
                pass
            if os.path.isfile(os.path.join(cwd, "app/server.py")):
                subprocess.Popen(["nohup", "python3", "-m", "app.server", "9006"],
                                 cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            ok = _port_open(9006)
            return ok, f"restart local app.server 9006 (cwd={cwd}), verify port 9006 = {ok}"
        # 情况2：无监听进程但存在 app.server 残留进程（可探测 cwd）
        if not cwd:
            try:
                out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True,
                                     text=True, timeout=10)
                for line in out.stdout.splitlines():
                    if "app.server 9006" in line or "app.server 9006" in line:
                        pid = line.split()[0]
                        if pid.isdigit():
                            c = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
                                               capture_output=True, text=True, timeout=10)
                            for cl in c.stdout.splitlines():
                                if cl.startswith("n/"):
                                    cwd = cl[2:]
                                    break
                        break
            except Exception:  # noqa: BLE001
                pass
        if cwd and os.path.isfile(os.path.join(cwd, "app/server.py")):
            try:
                subprocess.run(["pkill", "-f", r"app\.server 9006"], capture_output=True,
                               text=True, timeout=10)
                time.sleep(1)
            except Exception:  # noqa: BLE001
                pass
            subprocess.Popen(["nohup", "python3", "-m", "app.server", "9006"],
                             cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            ok = _port_open(9006)
            return ok, f"restart app.server 9006 (cwd={cwd}), verify port 9006 = {ok}"
        # 情况3：contract-compare 项目
        if not os.path.isdir(root):
            return _port_open(9006), f"project dir not found ({root}), no restart performed, port 9006 open={_port_open(9006)}"
        # 精确匹配 contract-compare 相关进程（禁止宽泛 pkill -f "9006"）
        subprocess.run(["pkill", "-f", "contract-compare"], capture_output=True, text=True, timeout=10)
        subprocess.run(["pkill", "-f", "uvicorn.*9006"], capture_output=True, text=True, timeout=10)
        time.sleep(1)
        # 检查常见的入口文件
        candidates = [os.path.join(root, "main.py"), os.path.join(root, "app/main.py"),
                      os.path.join(root, "run.py"), os.path.join(root, "run.sh")]
        cmd = None
        for c in candidates:
            if os.path.isfile(c):
                if c.endswith(".sh"):
                    cmd = ["bash", c]
                else:
                    cmd = ["nohup", "python3", c.replace(root + "/", ""),
                           "--host", "0.0.0.0", "--port", "9006"]
                break
        if cmd:
            subprocess.Popen(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        ok = _port_open(9006)
        return ok, f"restart contract-compare, verify port 9006 = {ok}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def act_recycle_container(entity_name: str, entity_attrs: dict) -> tuple:
    cname = entity_attrs.get("name", entity_name)
    try:
        subprocess.run(["docker", "restart", cname], capture_output=True, text=True, timeout=30)
        time.sleep(2)
        out = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", cname],
                             capture_output=True, text=True, timeout=10)
        ok = out.returncode == 0 and "running" in out.stdout.lower()
        return ok, f"docker restart {cname}, state = {out.stdout.strip()}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def act_cleanup_disk(_entity_name: str, _entity_attrs: dict) -> tuple:
    """安全清理磁盘：/tmp 与 /var/log 中大于 3 天的文件，以及 docker 悬空镜像"""
    try:
        cleaned = []
        # /tmp
        subprocess.run(["find", "/tmp", "-type", "f", "-mtime", "+3", "-delete"],
                       capture_output=True, text=True, timeout=30)
        cleaned.append("/tmp old files")
        # /var/log
        subprocess.run(["find", "/var/log", "-type", "f", "-name", "*.log.*", "-mtime", "+7", "-delete"],
                       capture_output=True, text=True, timeout=30)
        cleaned.append("/var/log rotated logs")
        # docker dangling
        out = subprocess.run(["docker", "system", "prune", "-f"],
                             capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            cleaned.append("docker system prune")
        return True, "cleaned: " + ", ".join(cleaned)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def act_restore_db(_entity_name: str, _entity_attrs: dict) -> tuple:
    """数据库异常时重建知识库索引作为恢复动作（最轻量安全的恢复方式）"""
    try:
        # 仅重建 sqlite 索引，不删数据
        db_path = db.DB_PATH
        conn = db._get_conn()
        try:
            conn.execute("ANALYZE")
            conn.commit()
        finally:
            conn.close()
        return True, f"ANALYZE sqlite db {db_path}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def act_restart_self(_entity_name: str, _entity_attrs: dict) -> tuple:
    """重启 neuops 自身服务（开发测试环境慎用）"""
    try:
        subprocess.run(["pkill", "-f", "uvicorn.*9007"], capture_output=True, text=True, timeout=10)
        time.sleep(1)
        subprocess.Popen(["nohup", "python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9007"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        return _port_open(9007), "restart neuops on port 9007"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


def _verify_alert_resolved(incident: dict) -> bool:
    """验证告警/故障是否已恢复：读取当前最新指标/实体状态"""
    etype = incident.get("entity_type", "")
    ename = incident.get("entity_name", "")
    rule_name = incident.get("rule_name", "")
    # 日志类故障：最近窗口内错误日志数回落到阈值以下视为恢复
    if etype == "log" or "log_error" in rule_name:
        try:
            window = 5
            n = db.ops_count_logs(minutes=window, level="error", source_prefix="app:")
            return n < 10
        except Exception:  # noqa: BLE001
            return False
    # 应用/端口类：直接探测端口
    if ename == "contract-compare":
        return _port_open(9006)
    if ename == "neuops-agent":
        return _port_open(9007)
    # 容器类
    if etype == "container":
        try:
            out = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", ename],
                                 capture_output=True, text=True, timeout=10)
            return out.returncode == 0 and "running" in out.stdout.lower()
        except Exception:  # noqa: BLE001
            return False
    # 通用：检查对应实体当前状态为 running
    e = db.ops_get_entity(incident.get("alert_id", ""))
    if e and e.get("status") == "running":
        return True
    # 通过 entity_name 模糊匹配
    for ent in db.ops_get_entities(etype):
        if ename in ent["name"] or ent["name"] in ename:
            return ent.get("status") == "running"
    # CPU/内存/磁盘类：检查最新值是否低于阈值
    metric_map = {
        "cpu_percent": "cpu_threshold", "mem_percent": "mem_threshold", "disk_percent": "disk_threshold"
    }
    for m, cfg in metric_map.items():
        if m in rule_name or m.replace("_percent", "") in rule_name:
            try:
                thr = float(db.db_get_setting(cfg, "90"))
            except ValueError:
                thr = 90
            latest = db.ops_get_latest_value(etype, ename, m)
            return latest < thr
    return False


# ─────────────── 自愈调度与状态机 ───────────────

def act_code_heal(entity_name: str, entity_attrs: dict) -> tuple:
    """白名单动作：代码级自愈（发现→修复→测试→发布→验证→回滚），委托 ops_code_heal"""
    from . import ops_code_heal
    return ops_code_heal.act_code_heal(entity_name, entity_attrs)


def _choose_action(incident: dict) -> str:
    """根据实体类型/规则名选择白名单修复动作"""
    etype = incident.get("entity_type", "")
    ename = incident.get("entity_name", "")
    rule = incident.get("rule_name", "")
    # 日志/代码类故障 → 代码级自愈
    if etype == "log" or "log_error" in rule or "code" in rule.lower():
        return "code_heal"
    if etype == "application":
        if "contract-compare" in ename or "9006" in rule:
            return "restart_9006"
        if "neuops" in ename:
            return "restart_self"
        return "restart_service"
    if etype == "container":
        return "recycle_container"
    if etype == "database":
        if "contract-compare" in ename:
            return "restart_9006"
        return "restore_db"
    if etype == "server" and ("disk_percent" in rule or "disk" in rule):
        return "cleanup_disk"
    return "restart_service"


def _execute_action(incident_id: str, action: str, entity_name: str, entity_attrs: dict) -> tuple:
    if action not in HEAL_ACTIONS:
        return False, f"护栏拦截：动作 {action} 不在白名单 {list(HEAL_ACTIONS.keys())} 中"
    func_name = HEAL_ACTIONS[action]
    func = globals()[func_name]
    _log(incident_id, f"执行动作 {action}")
    ok, msg = func(entity_name, entity_attrs)
    _log(incident_id, f"动作结果 ok={ok} msg={msg}")
    return ok, msg


def process_incident(incident_id: str):
    """处理一个已检测到的自愈事件（由 alert_engine 或自愈线程调用）"""
    inc = db.incident_get(incident_id)
    if not inc:
        return
    if inc.get("state") in ("recovered", "manual", "failed"):
        return
    if not _is_enabled():
        _log(incident_id, "自愈开关关闭，仅记录不执行")
        db.incident_update(incident_id, state="manual", message="自愈开关关闭，升级人工",
                           updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return

    db.incident_update(incident_id, state="repairing", updated_at=_now())
    feishu_notify.notify_incident(db.incident_get(incident_id))

    action = _choose_action(inc)
    db.incident_update(incident_id, fix_action=action, updated_at=_now())

    # 获取实体属性
    entity_name = inc.get("entity_name", "")
    entity_attrs = {}
    for ent in db.ops_get_entities(inc.get("entity_type", "")):
        if ent["name"] == entity_name or ent["id"] == str(inc.get("alert_id", "")):
            entity_attrs = dict(ent.get("attrs", {}))
            break
    # 代码级自愈需要 incident_id 定位事件
    entity_attrs["incident_id"] = incident_id

    # 远程探针服务器故障：自愈动作只作用于监控中心本机，跳过并升级人工
    if entity_attrs.get("remote_host"):
        _log(incident_id, f"远程服务器 {entity_attrs.get('remote_host')} 故障，跳过本机自愈动作，升级人工")
        db.incident_update(incident_id, state="manual",
                           message="远程探针服务器故障，自愈动作不作用于远程主机，升级人工处理",
                           updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return

    ok, msg = _execute_action(incident_id, action, entity_name, entity_attrs)

    # 代码级自愈动作内部已完成 修复→测试→发布→验证→(回滚) 全流程并更新状态，直接采信
    if action == "code_heal":
        cur = db.incident_get(incident_id)
        if cur.get("state") == "recovered":
            logger.info("[self-heal] code_heal recovered %s", incident_id)
            return
        if cur.get("state") == "manual":
            _log(incident_id, "代码自愈已升级人工")
            return
        # 兜底：未到终态则继续标准 verifying 流程
        db.incident_update(incident_id, state="verifying", updated_at=_now())
        if _verify_alert_resolved(db.incident_get(incident_id)):
            db.incident_update(incident_id, state="recovered", resolved_at=_now(), updated_at=_now())
            feishu_notify.notify_incident(db.incident_get(incident_id))
            return
        db.incident_update(incident_id, state="manual", updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        return

    # 验证
    db.incident_update(incident_id, state="verifying", updated_at=_now())
    resolved = _verify_alert_resolved(inc)
    _log(incident_id, f"验证结果 resolved={resolved}")

    if resolved:
        db.incident_update(incident_id, state="recovered", resolved_at=_now(), updated_at=_now())
        feishu_notify.notify_incident(db.incident_get(incident_id))
        logger.info("[self-heal] recovered %s", incident_id)
        return

    # 失败：重试
    retry = (inc.get("retry_count", 0) or 0) + 1
    db.incident_update(incident_id, retry_count=retry, updated_at=_now())
    if retry <= _max_retry():
        _log(incident_id, f"验证未通过，第 {retry}/{_max_retry()} 次重试")
        # 再次调度（下一次自愈循环会重新处理）
        return

    db.incident_update(incident_id, state="failed", updated_at=_now())
    feishu_notify.notify_incident(db.incident_get(incident_id))
    # 再升级为 manual（避免无限循环）
    db.incident_update(incident_id, state="manual", updated_at=_now())
    feishu_notify.notify_incident(db.incident_get(incident_id))


def create_incident_from_alert(alert_id: int, rule_name: str, entity_type: str,
                               entity_name: str, severity: str, message: str) -> dict:
    """从告警创建自愈事件；若该告警已有未恢复事件则返回现有"""
    existing = db._query_rows(
        "SELECT id FROM incidents WHERE alert_id = ? AND state NOT IN ('recovered', 'failed', 'manual')",
        (alert_id,))
    if existing:
        return db.incident_get(existing[0]["id"])
    incident_id = "INC-" + uuid.uuid4().hex[:8].upper()
    return db.incident_create(incident_id, alert_id, rule_name, entity_type, entity_name,
                              severity, message, _now())


# ─────────────── 后台自愈循环 ───────────────

class SelfHealEngine:
    """自愈引擎：后台扫描未处理/验证未通过的 incidents 并驱动状态机"""

    def __init__(self, interval: int = 20):
        self.interval = interval
        self._thread = None
        self._stop = threading.Event()

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("[self-heal] tick error")

    def _tick(self):
        # 处理 detected / verifying（失败重试）
        rows = db._query_rows(
            "SELECT id FROM incidents WHERE state IN ('detected','verifying') ORDER BY created_at ASC LIMIT 20")
        for row in rows:
            process_incident(row["id"])

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ops-self-heal", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self


# 模块级实例（由 main.py 启动）
_self_heal_engine = SelfHealEngine()


def get_engine() -> SelfHealEngine:
    return _self_heal_engine
