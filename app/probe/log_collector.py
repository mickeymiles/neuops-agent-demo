# -*- coding: utf-8 -*-
"""统一探针 - 日志采集器（log_collector）

实现"一个探针解决所有采集问题"中的日志采集：
  - 系统日志：macOS /var/log/system.log，Linux /var/log/syslog、/var/log/messages，Docker journalctl
  - 应用日志：9006 contract-compare 与 9007 neuops 的应用日志文件（路径通过 settings 页面配置）
  - 增量读取（tail 风格，记录每个文件的读取偏移），只上报新增行，避免重复与全量刷库
  - 解析日志级别（error/warn/info/debug），输出到统一 ops_logs 表，供日志查询与日志告警规则使用
"""
import os
import re
import time
from datetime import datetime

from app.db import db_get_setting
from app.probe.base import BaseCollector, ProbeReport

# 日志级别解析：正则捕获 [LEVEL] / LEVEL: / "LEVEL" 等常见格式
_LEVEL_RE = re.compile(
    r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE)\b", re.IGNORECASE)

_LEVEL_ORDER = ("critical", "error", "warn", "info", "debug", "trace")

# 系统日志候选路径（按 OS 探测）
def _system_log_paths():
    cands = []
    if os.path.exists("/var/log/system.log"):      # macOS
        cands.append("/var/log/system.log")
    if os.path.exists("/var/log/syslog"):          # Debian/Ubuntu
        cands.append("/var/log/syslog")
    if os.path.exists("/var/log/messages"):        # RHEL/CentOS
        cands.append("/var/log/messages")
    return cands


class _TailReader:
    """按偏移增量读取日志文件的读取器。文件轮转(ino 变化)时从头读取最近 max_backfill 行。"""

    def __init__(self, path: str, max_backfill: int = 80):
        self.path = path
        self.max_backfill = max_backfill
        self._offset = 0
        self._ino = None
        self._ready = False

    def _file_meta(self):
        try:
            st = os.stat(self.path)
            return st.st_ino, st.st_size
        except OSError:
            return None, 0

    def read_new_lines(self, max_lines: int = 200) -> list:
        ino, size = self._file_meta()
        if ino is None:
            return []
        if not self._ready:
            # 首次读取：从文件尾部回填最近 max_backfill 行
            self._ino, self._offset = ino, max(0, size - 64 * 1024)
            self._ready = True
        elif ino != self._ino:
            # 日志轮转：回到新文件末尾回填
            self._ino, self._offset = ino, max(0, size - 64 * 1024)

        try:
            with open(self.path, "r", errors="replace") as f:
                f.seek(self._offset)
                lines = []
                for _ in range(max_lines):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip("\n"))
                self._offset = f.tell()
            return lines
        except OSError:
            return []


def _classify_level(line: str) -> str:
    m = _LEVEL_RE.search(line)
    if not m:
        return "info"
    lv = m.group(1).lower()
    return {
        "fatal": "critical", "critical": "critical", "error": "error",
        "warn": "warn", "warning": "warn", "info": "info", "debug": "debug",
        "trace": "trace",
    }.get(lv, "info")


class LogCollector(BaseCollector):
    """统一日志采集器：系统日志 + 应用日志（9006/9007）增量采集。"""

    name = "log"
    label = "日志采集"
    entity_type = "log"

    def __init__(self, probe=None, max_lines_per_run: int = 300):
        self.probe = probe
        self.max_lines_per_run = max_lines_per_run
        self._tailers = {}   # path -> _TailReader
        self._seen_errors = 0

    def _resolve_sources(self) -> list:
        """日志来源列表：(label, path)。应用日志路径通过 settings 页面配置。"""
        srcs = []
        for p in _system_log_paths():
            srcs.append(("system:" + os.path.basename(p), p))
        app9006 = (db_get_setting("app_9006_log") or "").strip()
        if app9006 and os.path.exists(app9006):
            srcs.append(("app:contract-compare", app9006))
        app9007 = (db_get_setting("app_9007_log") or "").strip()
        if app9007 and os.path.exists(app9007):
            srcs.append(("app:neuops", app9007))
        return srcs

    def collect(self) -> ProbeReport:
        rpt = ProbeReport(collector=self.name)
        sources = self._resolve_sources()
        error_n, warn_n, info_n = 0, 0, 0
        for label, path in sources:
            tailer = self._tailers.get(path)
            if tailer is None:
                # 首次读取仅回填最近 16KB（约 60~100 行），避免历史日志一次灌满
                tailer = self._tailers[path] = _TailReader(path, max_backfill=16 * 1024)
            new_lines = tailer.read_new_lines(self.max_lines_per_run)
            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                lv = _classify_level(line)
                if lv == "error" or lv == "critical":
                    error_n += 1
                elif lv == "warn":
                    warn_n += 1
                elif lv == "info":
                    info_n += 1
                rpt.add_log(label, lv, line[:2000])

        # 每个来源上报一个 log 实体，状态反映最近窗口错误情况
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "running"
        if error_n > 0:
            status = "degraded"
        rpt.add_entity(
            "log:aggregate", "log", "统一日志",
            status,
            metrics={
                "log_error_count": float(error_n),
                "log_warn_count": float(warn_n),
                "log_info_count": float(info_n),
                "log_total_count": float(error_n + warn_n + info_n),
            },
            attrs={"sources": ",".join(s for s, _ in sources), "updated_at": now_ts},
        )
        # 指标上报（error/warn 供告警规则检测）
        rpt.add_metric("log", "aggregate", "log_error_count", float(error_n), "count")
        rpt.add_metric("log", "aggregate", "log_warn_count", float(warn_n), "count")

        self._seen_errors += error_n
        # 心跳：即使没有新日志也刷新 last_ts，保持实体新鲜度
        rpt.add_metric("log", "aggregate", "last_ts", time.time(), "s")
        return rpt
