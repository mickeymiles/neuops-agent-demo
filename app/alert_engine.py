"""后台告警检测引擎：定时扫描 llm_calls + 统一探针真实 ops 指标，生成/解除告警并触发自愈"""

import time
from datetime import datetime, timedelta

from .db import _agent_name_map, _db_lock, _get_conn, _query_rows

DEFAULT_ALERT_RULES = [
    {"id": "rule-001", "name": "LLM 调用错误率过高", "metric": "llm_error", "target": "", "threshold": 10.0,
     "window_min": 30, "severity": "critical", "desc": "近 30 分钟 LLM 调用错误率超过 10%"},
    {"id": "rule-002", "name": "慢 LLM 调用（对应慢 SQL）", "metric": "slow_call", "target": "", "threshold": 30000.0,
     "window_min": 30, "severity": "warning", "desc": "近 30 分钟平均调用耗时超过 30s"},
    {"id": "rule-003", "name": "Token 用量突增", "metric": "cost_burst", "target": "", "threshold": 100000.0,
     "window_min": 60, "severity": "warning", "desc": "近 60 分钟 Token 用量超过 10 万"},
    {"id": "rule-004", "name": "单会话 Token 超限", "metric": "conv_overrun", "target": "", "threshold": 50000.0,
     "window_min": 60, "severity": "info", "desc": "单个会话近 60 分钟 Token 超过 5 万"},
    {"id": "rule-005", "name": "智能体长期不活跃", "metric": "agent_idle", "target": "emp-001", "threshold": 2.0,
     "window_min": 60, "severity": "warning", "desc": "运维巡检专家 2 天无调用"},

    # ── 统一探针真实系统指标告警（ops 系列）──
    {"id": "rule-ops-001", "name": "服务器 CPU 使用率过高", "metric": "cpu_percent", "target": "server", "threshold": 90.0,
     "window_min": 2, "severity": "critical", "desc": "服务器 CPU 使用率超过阈值"},
    {"id": "rule-ops-002", "name": "服务器内存使用率过高", "metric": "mem_percent", "target": "server", "threshold": 90.0,
     "window_min": 2, "severity": "critical", "desc": "服务器内存使用率超过阈值"},
    {"id": "rule-ops-003", "name": "磁盘使用率过高", "metric": "disk_percent", "target": "server", "threshold": 90.0,
     "window_min": 2, "severity": "critical", "desc": "任意分区磁盘使用率超过阈值"},
    {"id": "rule-ops-004", "name": "应用健康检查失败", "metric": "health", "target": "application", "threshold": 1.0,
     "window_min": 1, "severity": "critical", "desc": "应用 HTTP 健康检查失败"},
    {"id": "rule-ops-005", "name": "数据库健康检查失败", "metric": "health", "target": "database", "threshold": 1.0,
     "window_min": 1, "severity": "critical", "desc": "数据库健康检查失败"},
    {"id": "rule-ops-006", "name": "中间件健康检查失败", "metric": "health", "target": "middleware", "threshold": 1.0,
     "window_min": 1, "severity": "warning", "desc": "中间件健康检查失败"},
    {"id": "rule-ops-007", "name": "应用日志错误突增", "metric": "log_error", "target": "log", "threshold": 10.0,
     "window_min": 5, "severity": "warning", "desc": "最近 5 分钟 ERROR/CRITICAL 日志超过阈值（疑似代码级故障，触发代码自愈）"},
]


def seed_alert_rules():
    """导入默认告警规则（幂等 upsert，新增规则在启动时自动补齐；保留用户已改配置）"""
    with _db_lock:
        conn = _get_conn()
        try:
            for r in DEFAULT_ALERT_RULES:
                # 已存在的规则只补齐新字段，不覆盖用户修改的阈值/开关
                row = conn.execute("SELECT id FROM alert_rules WHERE id=?", (r["id"],)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE alert_rules SET name=?, metric=?, target=?, window_min=?, severity=?, desc=? WHERE id=?",
                        (r["name"], r["metric"], r["target"], r["window_min"], r["severity"], r["desc"], r["id"]))
                else:
                    conn.execute(
                        "INSERT INTO alert_rules (id, name, metric, target, threshold, window_min, severity, enabled, desc) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (r["id"], r["name"], r["metric"], r["target"], r["threshold"], r["window_min"],
                         r["severity"], 1, r["desc"]))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('alert_rules_seeded', '1')")
            conn.commit()
        finally:
            conn.close()


def _process_alert(rule, value, message):
    """根据规则当前值决定：触发新告警 / 保持 / 回落则置为 resolved"""
    firing = value >= (rule["threshold"] or 0)
    existing = _query_rows("SELECT id FROM alerts WHERE rule_id=? AND target=? AND status='firing'",
                           (rule["id"], rule["target"] or ""))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target_name = _agent_name_map().get(rule["target"], rule["target"] or "全局")
    with _db_lock:
        conn = _get_conn()
        try:
            if firing:
                if not existing:
                    conn.execute(
                        "INSERT INTO alerts (rule_id, rule_name, severity, metric, target, target_name, status, message, value, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (rule["id"], rule["name"], rule["severity"], rule["metric"], rule["target"], target_name,
                         "firing", message, value, now))
            elif existing:
                for e in existing:
                    conn.execute("UPDATE alerts SET status='resolved', resolved_at=? WHERE id=?", (now, e["id"]))
            conn.commit()
        finally:
            conn.close()


def _run_alert_checks():
    """对每条启用的规则计算窗口指标并与阈值比较（智能体 APM 业务告警检测）"""
    rules = _query_rows("SELECT * FROM alert_rules WHERE enabled=1")
    now = datetime.now()
    for r in rules:
        try:
            metric, target = r["metric"], r["target"] or ""
            window_min = r["window_min"] or 60
            since = (now - timedelta(minutes=window_min)).strftime("%Y-%m-%d %H:%M:%S")
            if metric == "llm_error":
                calls = _query_rows("SELECT employee_id, error FROM llm_calls WHERE created_at>=?", (since,))
                if target:
                    calls = [c for c in calls if c["employee_id"] == target]
                if not calls:
                    continue
                errs = sum(1 for c in calls if c.get("error"))
                rate = errs / len(calls) * 100
                _process_alert(r, rate, f"近 {window_min} 分钟 LLM 调用错误率 {rate:.1f}%（{errs}/{len(calls)}）")
            elif metric == "slow_call":
                calls = _query_rows("SELECT employee_id, latency_ms FROM llm_calls WHERE created_at>=?", (since,))
                if target:
                    calls = [c for c in calls if c["employee_id"] == target]
                ok = [c for c in calls if (c["latency_ms"] or 0) > 0]
                if not ok:
                    continue
                avg = sum(c["latency_ms"] for c in ok) / len(ok)
                _process_alert(r, avg, f"近 {window_min} 分钟平均调用耗时 {int(avg)}ms（阈值 {int(r['threshold'])}ms）")
            elif metric == "cost_burst":
                calls = _query_rows("SELECT employee_id, total_tokens FROM llm_calls WHERE created_at>=?", (since,))
                if target:
                    calls = [c for c in calls if c["employee_id"] == target]
                tokens = sum(c["total_tokens"] or 0 for c in calls)
                _process_alert(r, tokens, f"近 {window_min} 分钟 Token 用量 {tokens}（阈值 {int(r['threshold'])}）")
            elif metric == "conv_overrun":
                calls = _query_rows("SELECT conversation_id, total_tokens FROM llm_calls WHERE created_at>=?", (since,))
                agg = {}
                for c in calls:
                    agg[c["conversation_id"]] = agg.get(c["conversation_id"], 0) + (c["total_tokens"] or 0)
                if not agg:
                    continue
                worst_cid, worst_tk = max(agg.items(), key=lambda x: x[1])
                _process_alert(r, worst_tk, f"会话 {worst_cid} 近 {window_min} 分钟 Token 用量 {worst_tk}（阈值 {int(r['threshold'])}）")
            elif metric == "agent_idle" and target:
                calls = _query_rows("SELECT created_at FROM llm_calls WHERE employee_id=?", (target,))
                last = max((c["created_at"] or "") for c in calls) if calls else ""
                if last:
                    idle_days = (now - datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")).days
                else:
                    idle_days = 999
                _process_alert(r, idle_days, f"智能体 {_agent_name_map().get(target, target)} 已 {idle_days} 天无调用（阈值 {int(r['threshold'])} 天）")
            # ── 统一探针真实系统指标（ops 系列）──
            elif metric == "cpu_percent":
                _check_ops_metric(r, "server", "cpu_percent", "cpu_percent")
            elif metric == "mem_percent":
                _check_ops_metric(r, "server", "mem_percent", "mem_percent")
            elif metric == "disk_percent":
                _check_ops_disk(r)
            elif metric == "health" and target in ("application", "database", "middleware", "container"):
                _check_ops_health(r, target)
            elif metric == "log_error":
                _check_ops_logs(r)
        except Exception:
            pass


def _check_ops_metric(rule, entity_type: str, entity_name_prefix: str, metric: str):
    """检查统一探针采集的实体实时指标是否超阈值，命中则生成告警并触发自愈"""
    from . import db
    threshold = float(rule["threshold"] or 0)
    snapshot = db.ops_get_latest_snapshot()
    for (etype, ename), m in snapshot.items():
        if etype != entity_type or not ename.startswith(entity_name_prefix):
            continue
        value = m.get(metric)
        if value is None:
            continue
        if value >= threshold:
            _process_alert_ops(rule, value, f"{ename} {metric}={value:.1f}%（阈值 {threshold:.0f}%）", etype, ename)


def _check_ops_disk(rule):
    """检查各分区磁盘使用率，取最大分区判断"""
    from . import db
    threshold = float(rule["threshold"] or 0)
    snapshot = db.ops_get_latest_snapshot()
    worst = None
    for (etype, ename), m in snapshot.items():
        if etype != "server":
            continue
        for k, v in m.items():
            if k.endswith("_percent") and k.startswith("disk_"):
                if v >= threshold and (worst is None or v > worst[1]):
                    worst = (f"{ename} [{k}]", v)
    if worst:
        _process_alert_ops(rule, worst[1], f"{worst[0]} 磁盘使用率={worst[1]:.1f}%（阈值 {threshold:.0f}%）",
                           "server", "server")


def _check_ops_health(rule, entity_type: str):
    """检查实体健康状态（health=1 健康 / 0 异常，低于阈值视为故障）"""
    from . import db
    threshold = float(rule["threshold"] or 1.0)
    for ent in db.ops_get_entities(entity_type):
        m = ent.get("metrics", {})
        health = m.get("health", 1 if ent.get("status") == "running" else 0)
        if health < threshold:
            _process_alert_ops(rule, health,
                               f"{ent['name']} 健康检查失败，状态 {ent.get('status', 'unknown')}",
                               entity_type, ent["name"])


def _check_ops_logs(rule):
    """检查最近窗口内 ERROR/CRITICAL 日志数量，超过阈值触发告警并进入代码级自愈"""
    from . import config, db
    threshold = float(rule["threshold"] or 0)
    window = int(rule.get("window_min") or config.LOG_ERROR_WINDOW_MIN)
    # 只统计应用日志（app: 源），排除 system 系统日志噪音，避免误报
    n = db.ops_count_logs(minutes=window, level="error", source_prefix="app:")
    if n >= threshold:
        # 附带最近一条错误日志，便于代码自愈诊断定位
        last = db.ops_get_logs(source="", level="error", minutes=window, limit=1)
        hint = last[0]["message"][:300] if last else ""
        _process_alert_ops(rule, n,
                           f"最近 {window} 分钟采集到 {n} 条错误日志（阈值 {threshold:.0f}）"
                           + (f"；最近错误：{hint}" if hint else ""),
                           "log", "log")


def _process_alert_ops(rule, value, message, entity_type: str, entity_name: str):
    """生成 ops 告警 + 触发飞书通知 + 创建自愈事件

    判定方向：cpu/mem/disk 等百分比类指标「大于等于阈值」触发；
    health 类指标（值域 0/1）通过 inverted 规则判定「低于阈值」触发。
    """
    rule_id = rule["id"]
    is_health = "health" in str(rule_id) or rule.get("metric") == "health"
    threshold = float(rule["threshold"] or 0)
    firing = (value < threshold) if is_health else (value >= threshold)
    if not firing:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = _query_rows(
        "SELECT id FROM alerts WHERE rule_id=? AND status='firing' AND message=?",
        (rule["id"], message))
    alert_id = None
    with _db_lock:
        conn = _get_conn()
        try:
            if not existing:
                cur = conn.execute(
                    "INSERT INTO alerts (rule_id, rule_name, severity, metric, target, target_name, status, message, value, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (rule["id"], rule["name"], rule["severity"], rule["metric"], entity_name, entity_name,
                     "firing", message, value, now))
                alert_id = cur.lastrowid
            else:
                alert_id = existing[0]["id"]
            conn.commit()
        finally:
            conn.close()
    if not alert_id:
        return
    # 飞书通知
    try:
        from . import feishu_notify
        feishu_notify.send_alert(rule["severity"], f"[NeuOps] {rule['name']}",
                                 f"{entity_type}/{entity_name}\n{message}",
                                 {"entity": entity_name, "metric": rule["metric"],
                                  "value": f"{value:.1f}", "threshold": rule["threshold"]})
    except Exception:
        pass
    # 触发自愈
    try:
        from . import ops_self_heal
        inc = ops_self_heal.create_incident_from_alert(
            alert_id, rule["name"], entity_type, entity_name, rule["severity"], message)
        if inc.get("state") in ("detected", "verifying"):
            ops_self_heal.process_incident(inc["id"])
    except Exception:
        pass


def _alert_engine_loop():
    """后台告警检测引擎：启动 15 秒后每 60 秒扫描一次"""
    time.sleep(15)
    while True:
        try:
            _run_alert_checks()
        except Exception:
            pass
        time.sleep(60)
