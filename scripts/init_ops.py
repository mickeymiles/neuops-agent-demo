# -*- coding: utf-8 -*-
"""初始化运维监控模块：建表 + 默认配置 + 首次全量采集

用法：
    python3 scripts/init_ops.py [--interval 30]
"""
import sys

sys.path.insert(0, ".")

from app import config  # noqa: E402
from app import db  # noqa: E402


def main():
    interval = config.OPS_PROBE_INTERVAL
    if "--interval" in sys.argv:
        try:
            interval = int(sys.argv[sys.argv.index("--interval") + 1])
        except (ValueError, IndexError):
            pass

    print("[init] 初始化 ops 表结构...")
    db.init_ops_db()

    print("[init] 写入默认配置...")
    defaults = {
        "probe_interval": str(interval),
        "retention_days": str(config.OPS_RETENTION_DAYS),
        "cpu_threshold": "90",
        "mem_threshold": "90",
        "disk_threshold": "90",
        "feishu_webhook": "",
        "feishu_secret": "",
    }
    for k, v in defaults.items():
        if not db.db_get_setting(k, ""):
            db.db_set_setting(k, v)
            print(f"  {k} = {v}")

    print("[init] 执行首次全量采集...")
    from app.probe import ProbeManager
    pm = ProbeManager(interval=interval)
    summary = pm.run_once()
    print(f"[init] 采集完成: {summary}")
    print("[init] 完成 ✅")


if __name__ == "__main__":
    main()
