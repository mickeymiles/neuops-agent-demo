# -*- coding: utf-8 -*-
"""数据库采集器：真实检测与健康检查

覆盖：
- 本机 neuops SQLite（neuops_sessions.db）：文件存在性 / 大小 / 打开查询测试
- 9006 系统数据库：SQLite 候选文件检测 + MySQL/PostgreSQL 端口探测（类型实证后可精确采集）
- 常见 SQLite 数据库文件（当前工作目录与数据目录）
"""
import os
import socket
import sqlite3

from .. import config
from .base import BaseCollector, ProbeReport


class DatabaseCollector(BaseCollector):
    name = "database"
    label = "数据库采集"
    entity_type = "database"

    def _port_open(self, port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _sqlite_health(self, path: str) -> tuple:
        """返回 (ok, size_mb, detail)"""
        try:
            size = os.path.getsize(path) / 1024 / 1024
            conn = sqlite3.connect(path, timeout=1)
            try:
                cur = conn.execute("SELECT 1")
                cur.fetchone()
                # 常用表数量
                tables = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            finally:
                conn.close()
            return True, size, f"{tables} tables"
        except Exception as e:  # noqa: BLE001
            return False, 0.0, str(e)

    def _probe_sqlite_candidates(self, candidates) -> dict:
        """扫描候选 SQLite 文件，返回 {path: (ok, size, detail)}"""
        out = {}
        for path in candidates:
            if os.path.isfile(path):
                out[path] = self._sqlite_health(path)
        return out

    def collect(self) -> ProbeReport:
        rpt = ProbeReport(collector=self.name)
        try:
            import socket as _s
            host = _s.gethostname()
        except Exception:
            host = "unknown"
        found_any = False

        # 1) 本机 neuops SQLite
        db_path = getattr(config, "DB_PATH", "neuops_sessions.db")
        if os.path.isfile(db_path):
            found_any = True
            ok, size, detail = self._sqlite_health(db_path)
            status = "running" if ok else "down"
            rpt.add_entity(f"database-{os.path.basename(db_path)}", "database",
                           f"neuops-sqlite [{os.path.basename(db_path)}]", status,
                           {"size_mb": round(size, 2), "health": 1 if ok else 0},
                           {"path": db_path, "engine": "sqlite", "detail": detail})
            rpt.add_metric("database", "neuops-sqlite", "size_mb", round(size, 2), "MB")
            rpt.add_metric("database", "neuops-sqlite", "health", 1 if ok else 0)
            rpt.add_relation(f"database-{os.path.basename(db_path)}", f"server-{host}", "hosted_on")

        # 2) 9006 系统数据库（SQLite 候选）
        for cand in getattr(config, "DB_9006_SQLITE_CANDIDATES", ()):
            if os.path.isfile(cand):
                found_any = True
                ok, size, detail = self._sqlite_health(cand)
                ent_id = f"database-9006-{os.path.basename(cand)}"
                rpt.add_entity(ent_id, "database",
                               f"contract-compare-db [{os.path.basename(cand)}]",
                               "running" if ok else "down",
                               {"size_mb": round(size, 2), "health": 1 if ok else 0},
                               {"path": cand, "engine": "sqlite", "detail": detail})
                rpt.add_metric("database", "contract-compare-db", "size_mb", round(size, 2), "MB")
                rpt.add_metric("database", "contract-compare-db", "health", 1 if ok else 0)
                rpt.add_relation(ent_id, f"server-{host}", "hosted_on")

        # 3) MySQL / PostgreSQL 端口探测（9006 系统可能使用的数据库）
        for engine, port in (("mysql", config.DB_9006_MYSQL_PORT),
                             ("postgresql", config.DB_9006_PG_PORT)):
            if self._port_open(port):
                found_any = True
                rpt.add_entity(f"database-{engine}", "database", engine,
                               "running", {"health": 1, "port": port},
                               {"engine": engine, "port": port})
                rpt.add_metric("database", engine, "health", 1)
                rpt.add_relation(f"database-{engine}", f"server-{host}", "hosted_on")

        # 4) 通用 SQLite 探测（数据目录下的 .db 文件）
        scan_dirs = [".", "data", "backend", "app"]
        seen = set()
        seen.add(os.path.abspath(db_path))
        for cand in getattr(config, "DB_9006_SQLITE_CANDIDATES", ()):
            seen.add(os.path.abspath(cand))
        for d in scan_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for fn in os.listdir(d):
                    if fn.endswith(".db") or fn.endswith(".sqlite"):
                        full = os.path.join(d, fn)
                        full_abs = os.path.abspath(full)
                        if full_abs in seen or not os.path.isfile(full):
                            continue
                        seen.add(full_abs)
                        ok, size, detail = self._sqlite_health(full)
                        found_any = True
                        ent_id = f"database-{fn}"
                        rpt.add_entity(ent_id, "database", fn,
                                       "running" if ok else "down",
                                       {"size_mb": round(size, 2), "health": 1 if ok else 0},
                                       {"path": full, "engine": "sqlite", "detail": detail})
                        rpt.add_metric("database", fn, "size_mb", round(size, 2), "MB")
                        rpt.add_metric("database", fn, "health", 1 if ok else 0)
                        rpt.add_relation(ent_id, f"server-{host}", "hosted_on")
            except OSError:
                continue

        if not found_any:
            rpt.ok = True  # 没有数据库也是一种有效状态，不报错
        return rpt
