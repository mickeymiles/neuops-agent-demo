# -*- coding: utf-8 -*-
"""运维监控域：设置 / 指标 / 日志 / 实体 / 关系"""

import json

from .base import (
    _db_lock,
    _get_conn,
    _query_one,
    _query_rows,
)

OPS_ENTITY_TYPES = ("server", "database", "network", "container", "middleware", "application")


def init_ops_db():
    """初始化运维监控表结构（统一探针采集的数据落库）"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_name TEXT NOT NULL DEFAULT '',
                    metric TEXT NOT NULL DEFAULT '',
                    value REAL NOT NULL DEFAULT 0,
                    unit TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_metrics_ts ON ops_metrics(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_metrics_ent ON ops_metrics(entity_type, entity_name, metric)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    metrics TEXT NOT NULL DEFAULT '{}',
                    attrs TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_entities_type ON ops_entities(type)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_relations (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    type TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (source, target, type)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ops_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_logs_ts ON ops_logs(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_logs_src ON ops_logs(source, level)")

            # 远程探针隔离列：scope 标识数据来源主机（空=监控中心本机，非空=远程探针主机名）
            for _tbl in ("ops_entities", "ops_relations"):
                _cols = {r[1] for r in conn.execute(f"PRAGMA table_info({_tbl})")}
                if "scope" not in _cols:
                    conn.execute(f"ALTER TABLE {_tbl} ADD COLUMN scope TEXT NOT NULL DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_entities_scope ON ops_entities(scope)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_relations_scope ON ops_relations(scope)")
            conn.commit()
        finally:
            conn.close()


# ---- settings 配置 ----


def db_get_setting(key: str, default: str = "") -> str:
    row = _query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def db_set_setting(key: str, value: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value))
            conn.commit()
        finally:
            conn.close()


def db_get_settings_all() -> dict:
    rows = _query_rows("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


# ---- ops_metrics 时序指标 ----


def ops_save_metric(ts: str, entity_type: str, entity_name: str,
                    metric: str, value: float, unit: str = ""):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO ops_metrics (ts, entity_type, entity_name, metric, value, unit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, entity_type, entity_name, metric, float(value), unit))
            conn.commit()
        finally:
            conn.close()


def ops_save_metrics(ts: str, items):
    """批量写时序指标。items: list[(entity_type, entity_name, metric, value, unit)]"""
    if not items:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executemany(
                "INSERT INTO ops_metrics (ts, entity_type, entity_name, metric, value, unit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(ts, it[0], it[1], it[2], float(it[3]), it[4]) for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_metrics(entity_type: str = "", entity_name: str = "",
                    metric: str = "", minutes: int = 10) -> list:
    """按实体/指标/时间窗查询时序数据，按时间正序"""
    where, args = ["ts >= datetime('now', ?)"], ["-" + str(minutes) + " minutes"]
    if entity_type:
        where.append("entity_type = ?")
        args.append(entity_type)
    if entity_name:
        where.append("entity_name = ?")
        args.append(entity_name)
    if metric:
        where.append("metric = ?")
        args.append(metric)
    rows = _query_rows(
        "SELECT ts, entity_type, entity_name, metric, value, unit FROM ops_metrics "
        "WHERE " + " AND ".join(where) + " ORDER BY ts ASC", tuple(args))
    return [dict(r) for r in rows]


def ops_get_latest_value(entity_type: str, entity_name: str, metric: str,
                         default: float = 0.0) -> float:
    row = _query_one(
        "SELECT value FROM ops_metrics WHERE entity_type = ? AND entity_name = ? AND metric = ? "
        "ORDER BY ts DESC LIMIT 1",
        (entity_type, entity_name, metric))
    return row["value"] if row else default


def ops_get_latest_snapshot() -> dict:
    """最新一轮采集快照：{entity_name: {metric: value}}，用于告警检测"""
    rows = _query_rows(
        "SELECT entity_type, entity_name, metric, value FROM ops_metrics m "
        "WHERE ts = (SELECT MAX(ts) FROM ops_metrics)")
    snap: dict = {}
    for r in rows:
        snap.setdefault((r["entity_type"], r["entity_name"]), {})[r["metric"]] = r["value"]
    return snap


def ops_cleanup_old_metrics(retention_days: int = 1) -> int:
    """清理超过保留期的时序指标，返回删除行数"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM ops_metrics WHERE ts < datetime('now', ?)",
                ("-" + str(retention_days) + " days",))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


# ---- ops_logs 统一日志（探针日志采集器写入）----


def ops_save_logs(items):
    """批量写日志条目。items: list[(ts, source, level, message)]"""
    if not items:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executemany(
                "INSERT INTO ops_logs (ts, source, level, message) VALUES (?, ?, ?, ?)",
                [(it[0], it[1], it[2], it[3]) for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_logs(source: str = "", level: str = "", minutes: int = 30,
                 limit: int = 500) -> list:
    """按来源/级别/时间窗倒序查询日志"""
    where, args = ["ts >= datetime('now', ?)"], ["-" + str(minutes) + " minutes"]
    if source:
        where.append("source = ?")
        args.append(source)
    if level:
        where.append("level = ?")
        args.append(level)
    rows = _query_rows(
        "SELECT ts, source, level, message FROM ops_logs "
        "WHERE " + " AND ".join(where) + " ORDER BY ts DESC, id DESC LIMIT ?",
        tuple(args + [int(limit)]))
    return [dict(r) for r in rows]


def ops_count_logs(minutes: int = 10, level: str = "", source_prefix: str = "") -> int:
    """统计最近窗口内指定级别（默认全部）日志条数，用于告警检测。

    source_prefix 仅统计匹配前缀的来源（如 "app:" 只看应用日志，
    排除系统 syslog 噪音，避免 "应用日志错误突增" 规则被系统错误误触发）。
    """
    where, args = ["ts >= datetime('now', ?)"], ["-" + str(minutes) + " minutes"]
    if level:
        where.append("level = ?")
        args.append(level)
    if source_prefix:
        where.append("source LIKE ?")
        args.append(source_prefix + "%")
    row = _query_one(
        "SELECT COUNT(*) AS n FROM ops_logs WHERE " + " AND ".join(where),
        tuple(args))
    return int(row["n"]) if row else 0


def ops_cleanup_old_logs(retention_days: int = 1) -> int:
    """清理超过保留期的日志，返回删除行数"""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM ops_logs WHERE ts < datetime('now', ?)",
                ("-" + str(retention_days) + " days",))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


# ---- ops_entities 本体实体 ----


def ops_upsert_entity(entity_id: str, etype: str, name: str, status: str,
                      metrics: dict, attrs: dict, ts: str):
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO ops_entities (id, type, name, status, metrics, attrs, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "status = excluded.status, metrics = excluded.metrics, "
                "attrs = excluded.attrs, updated_at = excluded.updated_at",
                (entity_id, etype, name, status,
                 json.dumps(metrics, ensure_ascii=False),
                 json.dumps(attrs, ensure_ascii=False), ts))
            conn.commit()
        finally:
            conn.close()


def ops_save_entities(ts: str, items, scope: str = ""):
    """全量重建实体；按来源（scope）隔离：scope 为空重建本机（scope=''），非空重建对应远程探针"""
    with _db_lock:
        conn = _get_conn()
        try:
            if scope:
                conn.execute("DELETE FROM ops_entities WHERE scope = ?", (scope,))
            else:
                conn.execute("DELETE FROM ops_entities WHERE scope = ''")
            if items:
                conn.executemany(
                    "INSERT INTO ops_entities (id, type, name, status, metrics, attrs, updated_at, scope) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [(it["id"], it["type"], it["name"], it.get("status", "unknown"),
                      json.dumps(it.get("metrics", {}), ensure_ascii=False),
                      json.dumps(it.get("attrs", {}), ensure_ascii=False), ts, scope)
                     for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_entities(etype: str = "") -> list:
    if etype:
        rows = _query_rows(
            "SELECT * FROM ops_entities WHERE type = ? ORDER BY name", (etype,))
    else:
        rows = _query_rows("SELECT * FROM ops_entities ORDER BY type, name")
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["metrics"] = json.loads(d.get("metrics") or "{}")
        except Exception:
            d["metrics"] = {}
        try:
            d["attrs"] = json.loads(d.get("attrs") or "{}")
        except Exception:
            d["attrs"] = {}
        out.append(d)
    return out


def ops_get_entity(entity_id: str) -> dict:
    for e in ops_get_entities():
        if e["id"] == entity_id:
            return e
    return {}


# ---- ops_relations 本体关系 ----


def ops_save_relations(ts: str, items, scope: str = ""):
    """全量重建关系；按来源（scope）隔离：scope 为空重建本机（scope=''），非空重建对应远程探针"""
    with _db_lock:
        conn = _get_conn()
        try:
            if scope:
                conn.execute("DELETE FROM ops_relations WHERE scope = ?", (scope,))
            else:
                conn.execute("DELETE FROM ops_relations WHERE scope = ''")
            if items:
                conn.executemany(
                    "INSERT INTO ops_relations (source, target, type, updated_at, scope) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [(it[0], it[1], it[2], ts, scope) for it in items])
            conn.commit()
        finally:
            conn.close()


def ops_get_relations() -> list:
    rows = _query_rows("SELECT source, target, type FROM ops_relations")
    return [dict(r) for r in rows]
