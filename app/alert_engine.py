"""后台告警检测引擎：定时扫描 llm_calls + 统一探针真实 ops 指标，生成/解除告警并发送飞书通知"""

import json
import time
from datetime import datetime, timedelta

from .db import _agent_name_map, _db_lock, _get_conn, _query_rows

DEFAULT_ALERT_RULES = [
    {"id": "rule-001", "name": "LLM 调用错误率过高", "metric": "llm_error", "target": "", "threshold": 10.0,
     "window_min": 30, "severity": "critical", "type": "fault", "desc": "近 30 分钟 LLM 调用错误率超过 10%"},
    {"id": "rule-002", "name": "慢 LLM 调用（对应慢 SQL）", "metric": "slow_call", "target": "", "threshold": 30000.0,
     "window_min": 30, "severity": "warning", "type": "perf", "desc": "近 30 分钟平均调用耗时超过 30s"},
    {"id": "rule-003", "name": "Token 用量突增", "metric": "cost_burst", "target": "", "threshold": 100000.0,
     "window_min": 60, "severity": "warning", "type": "prewarn", "desc": "近 60 分钟 Token 用量超过 10 万"},
    {"id": "rule-004", "name": "单会话 Token 超限", "metric": "conv_overrun", "target": "", "threshold": 50000.0,
     "window_min": 60, "severity": "info", "type": "prewarn", "desc": "单个会话近 60 分钟 Token 超过 5 万"},
    {"id": "rule-005", "name": "智能体长期不活跃", "metric": "agent_idle", "target": "emp-001", "threshold": 2.0,
     "window_min": 60, "severity": "warning", "type": "prewarn", "desc": "运维巡检专家 2 天无调用"},

    # ── 统一探针真实系统指标告警（ops 系列）──
    {"id": "rule-ops-001", "name": "服务器 CPU 使用率过高", "metric": "cpu_percent", "target": "server", "threshold": 90.0,
     "window_min": 2, "severity": "critical", "type": "perf", "desc": "服务器 CPU 使用率超过阈值"},
    {"id": "rule-ops-002", "name": "服务器内存使用率过高", "metric": "mem_percent", "target": "server", "threshold": 90.0,
     "window_min": 2, "severity": "critical", "type": "perf", "desc": "服务器内存使用率超过阈值"},
    {"id": "rule-ops-003", "name": "磁盘使用率过高", "metric": "disk_percent", "target": "server", "threshold": 90.0,
     "window_min": 2, "severity": "critical", "type": "perf", "desc": "任意分区磁盘使用率超过阈值"},
    {"id": "rule-ops-004", "name": "应用健康检查失败", "metric": "health", "target": "application", "threshold": 1.0,
     "window_min": 1, "severity": "critical", "type": "availability", "desc": "应用 HTTP 健康检查失败"},
    {"id": "rule-ops-005", "name": "数据库健康检查失败", "metric": "health", "target": "database", "threshold": 1.0,
     "window_min": 1, "severity": "critical", "type": "availability", "desc": "数据库健康检查失败"},
    {"id": "rule-ops-006", "name": "中间件健康检查失败", "metric": "health", "target": "middleware", "threshold": 1.0,
     "window_min": 1, "severity": "warning", "type": "availability", "desc": "中间件健康检查失败"},
    {"id": "rule-ops-007", "name": "应用日志错误突增", "metric": "log_error", "target": "log", "threshold": 10.0,
     "window_min": 5, "severity": "warning", "type": "fault", "desc": "最近 5 分钟 ERROR/CRITICAL 日志超过阈值（疑似代码级故障）"},
]

# 处置建议知识库：按告警类型/指标给出步骤化处置建议（后续可扩展为 LLM 自动生成）
SUGGESTIONS = {
    "fault": [
        "定位故障源：查看最近错误日志与调用链，确认异常发生在模型服务、工具还是业务代码",
        "按链路逐跳排查：检查 LLM 服务可用性 / 配额 / 鉴权，以及 MCP 工具与依赖服务状态",
        "采取恢复动作：重启异常服务或人工介入修复，必要时回滚最近变更",
        "验证恢复：观察错误率回落至阈值以下，并确认相关依赖服务健康",
    ],
    "perf": [
        "定位瓶颈：查看该实体的时序指标与 TOP 进程，确认是资源不足还是异常占用",
        "扩容或限流：按需提升资源配额，或对高消耗任务实施限流 / 排队",
        "优化负载：调整调度策略 / 清理冗余任务，降低资源峰值",
        "持续观测：确认指标回落并保持窗口期监控，必要时调整告警阈值",
    ],
    "prewarn": [
        "分析趋势：对比近期同窗口指标，判断是偶发波动还是持续上行",
        "定位消耗源：查看明细（会话 / 智能体 / 实体）找出主要贡献者",
        "提前干预：对接近上限的任务实施预算控制、上下文压缩或会话收敛",
        "跟踪确认：观察后续窗口是否回归基线，防止演变为故障",
    ],
    "availability": [
        "检查服务进程与端口：确认目标实体是否存活、健康检查端点是否可达",
        "查看服务日志：定位启动失败 / 依赖不可用的根因",
        "执行恢复：重启服务或拉起依赖，验证健康检查恢复",
        "确认无级联影响：检查上下游依赖实体状态，防止故障扩散",
    ],
    "business": [
        "核实业务影响：确认该告警对业务指标（成功率 / 转化 / 收入）的实际影响",
        "定位业务链路：沿业务链路分析异常发生的环节与责任方",
        "协调处置：按业务优先级安排修复或降级预案",
        "复盘优化：沉淀处置经验，优化业务规则与监控口径",
    ],
}

# 按指标映射建议（细粒度覆盖），未命中时回退到类型级建议
SUGGESTION_BY_METRIC = {
    "llm_error": [
        "检查 LLM API Key / 配额 / 鉴权是否异常，确认模型服务可用性",
        "查看错误明细（4xx/5xx / 限流 / 上下文超限），定位高频错误类型",
        "对故障模型实施降级 / 切换备用模型，或调整重试策略",
        "验证错误率回落，持续观察 1 个窗口周期",
    ],
    "slow_call": [
        "对比窗口内各智能体平均耗时，定位慢调用集中点",
        "检查是否命中大上下文 / 复杂工具链 / 模型端高负载",
        "优化提示词长度或拆分任务，必要时提高超时阈值",
        "观察耗时曲线回落，确认无新增慢调用",
    ],
    "cost_burst": [
        "按智能体 / 会话聚合 Token 消耗，定位突增来源",
        "检查是否存在循环调用 / 无界上下文增长",
        "对该会话 / 智能体实施预算上限或上下文压缩",
        "跟踪后续窗口用量，确认回归基线",
    ],
    "conv_overrun": [
        "定位超限会话，查看其输入输出与工具调用链",
        "控制上下文长度：启用摘要压缩 / 截断 / 拆分会话",
        "调整单会话 Token 上限或提醒用户收敛会话",
        "确认会话恢复正常，必要时归档历史会话",
    ],
    "agent_idle": [
        "确认该智能体是否仍需要启用，检查意图路由配置",
        "检查是否有消息被错误路由到其他智能体",
        "发送测试会话验证智能体可正常响应",
        "长期不活跃可考虑停用或归档，避免占用资源",
    ],
    "cpu_percent": [
        "定位高占用进程：查看 TOP 进程与线程，确认归属任务",
        "检查是否有异常任务 / 死循环 / 资源竞争",
        "按需扩容或对任务限流、错峰调度",
        "确认 CPU 回落并保持监控，必要时优化代码",
    ],
    "mem_percent": [
        "查看内存占用 TOP 进程，检查是否存在内存泄漏",
        "检查缓存 / 连接池配置是否合理",
        "评估扩容或重启服务释放内存",
        "持续观察内存曲线，确认无反复飙升",
    ],
    "disk_percent": [
        "查看磁盘分区占用，定位大文件 / 日志堆积来源",
        "清理过期日志与临时文件，或配置日志轮转",
        "评估磁盘扩容或数据迁移",
        "确认磁盘水位回落，设置更早的预警阈值",
    ],
    "health": [
        "检查目标实体进程 / 端口 / 健康检查端点状态",
        "查看实体日志定位启动失败或依赖故障根因",
        "重启服务或拉起依赖，验证健康检查恢复",
        "确认上下游实体无级联异常，恢复正常运行",
    ],
    "log_error": [
        "查看最近错误日志堆栈，定位异常代码位置",
        "按日志特征判断根因（依赖故障 / 数据异常 / 逻辑缺陷）",
        "人工介入修复：定位异常代码并回滚或修正",
        "验证错误日志不再增长，确认服务恢复正常",
    ],
}



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
                        "UPDATE alert_rules SET name=?, metric=?, target=?, window_min=?, severity=?, type=?, desc=? WHERE id=?",
                        (r["name"], r["metric"], r["target"], r["window_min"], r["severity"],
                         r.get("type", ""), r["desc"], r["id"]))
                else:
                    conn.execute(
                        "INSERT INTO alert_rules (id, name, metric, target, threshold, window_min, severity, type, enabled, desc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (r["id"], r["name"], r["metric"], r["target"], r["threshold"], r["window_min"],
                         r["severity"], r.get("type", ""), 1, r["desc"]))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('alert_rules_seeded', '1')")
            conn.commit()
        finally:
            conn.close()


def _alert_suggestion(rule) -> str:
    """按规则 metric 优先取细粒度建议，未命中则回退类型级建议，返回 JSON 数组字符串"""
    steps = SUGGESTION_BY_METRIC.get(rule.get("metric") or "")
    if not steps:
        steps = SUGGESTIONS.get(rule.get("type") or "", SUGGESTIONS["fault"])
    return json.dumps(steps, ensure_ascii=False)


def _process_alert(rule, value, message):
    """根据规则当前值决定：触发新告警 / 保持 / 回落则置为 resolved"""
    firing = value >= (rule["threshold"] or 0)
    existing = _query_rows("SELECT id FROM alerts WHERE rule_id=? AND target=? AND status='firing'",
                           (rule["id"], rule["target"] or ""))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target_name = _agent_name_map().get(rule["target"], rule["target"] or "全局")
    suggestion = _alert_suggestion(rule)
    with _db_lock:
        conn = _get_conn()
        try:
            if firing:
                if not existing:
                    conn.execute(
                        "INSERT INTO alerts (rule_id, rule_name, severity, type, metric, target, target_name, "
                        "entity_type, entity_name, status, message, value, suggestion, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rule["id"], rule["name"], rule["severity"], rule.get("type", ""), rule["metric"],
                         rule["target"], target_name, "agent", rule["target"] or "", "firing", message, value,
                         suggestion, now))
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
    """检查统一探针采集的实体实时指标是否超阈值，命中则生成告警并发送飞书通知"""
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
    """检查最近窗口内 ERROR/CRITICAL 日志数量，超过阈值触发告警"""
    from . import config, db
    threshold = float(rule["threshold"] or 0)
    window = int(rule.get("window_min") or config.LOG_ERROR_WINDOW_MIN)
    # 只统计应用日志（app: 源），排除 system 系统日志噪音，避免误报
    n = db.ops_count_logs(minutes=window, level="error", source_prefix="app:")
    if n >= threshold:
        # 附带最近一条错误日志，便于根因诊断定位
        last = db.ops_get_logs(source="", level="error", minutes=window, limit=1)
        hint = last[0]["message"][:300] if last else ""
        _process_alert_ops(rule, n,
                           f"最近 {window} 分钟采集到 {n} 条错误日志（阈值 {threshold:.0f}）"
                           + (f"；最近错误：{hint}" if hint else ""),
                           "log", "log")


def _process_alert_ops(rule, value, message, entity_type: str, entity_name: str):
    """生成 ops 告警 + 触发飞书通知

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
    suggestion = _alert_suggestion(rule)
    alert_id = None
    with _db_lock:
        conn = _get_conn()
        try:
            if not existing:
                cur = conn.execute(
                    "INSERT INTO alerts (rule_id, rule_name, severity, type, metric, target, target_name, "
                    "entity_type, entity_name, status, message, value, suggestion, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rule["id"], rule["name"], rule["severity"], rule.get("type", ""), rule["metric"],
                     entity_name, entity_name, entity_type, entity_name, "firing", message, value,
                     suggestion, now))
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


def _alert_engine_loop():
    """后台告警检测引擎：启动 15 秒后每 60 秒扫描一次"""
    time.sleep(15)
    while True:
        try:
            _run_alert_checks()
        except Exception:
            pass
        time.sleep(60)
