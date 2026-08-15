#!/usr/bin/env python3
"""
Mock 数据更新脚本
用于从真实运维系统拉取数据，更新 mock_data.py 中的 Mock 数据。

用法:
  python3 scripts/update_mock.py              # 从真实系统刷新所有 Mock 数据
  python3 scripts/update_mock.py --dry-run    # 仅打印将要更新的内容
  python3 scripts/update_mock.py --source prometheus  # 仅更新指标数据

数据源配置: 在 ~/.hermes/.env 或环境变量中设置:
  PROMETHEUS_URL=http://your-prometheus:9090
  ELASTICSEARCH_URL=http://your-es:9200
  CMDB_API_URL=http://your-cmdb/api
  ITSM_API_URL=http://your-itsm/api
  ALARM_API_URL=http://your-alarm/api
  JOB_API_URL=http://your-job-platform/api
"""

import os
import sys
import json
import argparse
from datetime import datetime


def fetch_prometheus_metrics():
    """从 Prometheus 拉取最新指标，更新 MOCK_METRICS"""
    url = os.getenv("PROMETHEUS_URL")
    if not url:
        print("[SKIP] PROMETHEUS_URL 未配置，跳过指标更新")
        return None

    # TODO: 真实 Prometheus 查询
    # import httpx
    # resp = httpx.get(f"{url}/api/v1/query", params={"query": '...'})
    # return resp.json()

    print("[TODO] Prometheus 查询待实现")
    print(f"       配置 PROMETHEUS_URL={url} 后，此处将自动拉取最新指标")
    return None


def fetch_elasticsearch_logs():
    """从 ES 拉取最新异常日志，更新 MOCK_LOGS"""
    url = os.getenv("ELASTICSEARCH_URL")
    if not url:
        print("[SKIP] ELASTICSEARCH_URL 未配置，跳过日志更新")
        return None

    # TODO: 真实 ES 查询
    print("[TODO] Elasticsearch 查询待实现")
    return None


def fetch_cmdb_topology():
    """从 CMDB 拉取资产拓扑，更新 MOCK_CMDB"""
    url = os.getenv("CMDB_API_URL")
    if not url:
        print("[SKIP] CMDB_API_URL 未配置，跳过 CMDB 更新")
        return None

    # TODO: 真实 CMDB API 查询
    print("[TODO] CMDB API 查询待实现")
    return None


def fetch_itsm_changes():
    """从 ITSM 拉取变更记录，更新 MOCK_CHANGES"""
    url = os.getenv("ITSM_API_URL")
    if not url:
        print("[SKIP] ITSM_API_URL 未配置，跳过变更记录更新")
        return None

    # TODO: 真实 ITSM API 查询
    print("[TODO] ITSM API 查询待实现")
    return None


def fetch_alarms():
    """从告警平台拉取告警，更新 MOCK_ALARMS"""
    url = os.getenv("ALARM_API_URL")
    if not url:
        print("[SKIP] ALARM_API_URL 未配置，跳过告警更新")
        return None

    # TODO: 真实告警 API 查询
    print("[TODO] 告警 API 查询待实现")
    return None


def update_mock_data_file(updates: dict):
    """将更新后的数据写回 mock_data.py"""
    # 读取当前 mock_data.py
    mock_path = os.path.join(os.path.dirname(__file__), "..", "mock_data.py")
    with open(mock_path, "r") as f:
        content = f.read()

    # TODO: 替换对应变量
    # 简单方案：用正则替换 MOCK_XXX = [...] 的内容
    # 复杂方案：AST 解析后重新生成

    print(f"[TODO] 写入 {mock_path}")
    print(f"       更新内容: {json.dumps(updates, ensure_ascii=False, indent=2)[:200]}...")


def main():
    parser = argparse.ArgumentParser(description="Mock 数据更新脚本")
    parser.add_argument("--dry-run", action="store_true", help="仅打印，不写入")
    parser.add_argument("--source", choices=["prometheus", "es", "cmdb", "itsm", "alarm", "all"],
                        default="all", help="指定更新源")
    args = parser.parse_args()

    print(f"=== Mock 数据更新脚本 ===")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"模式: {'DRY RUN (仅预览)' if args.dry_run else '写入更新'}")
    print()

    updates = {}

    if args.source in ("prometheus", "all"):
        metrics = fetch_prometheus_metrics()
        if metrics:
            updates["MOCK_METRICS"] = metrics

    if args.source in ("es", "all"):
        logs = fetch_elasticsearch_logs()
        if logs:
            updates["MOCK_LOGS"] = logs

    if args.source in ("cmdb", "all"):
        topo = fetch_cmdb_topology()
        if topo:
            updates["MOCK_CMDB"] = topo

    if args.source in ("itsm", "all"):
        changes = fetch_itsm_changes()
        if changes:
            updates["MOCK_CHANGES"] = changes

    if args.source in ("alarm", "all"):
        alarms = fetch_alarms()
        if alarms:
            updates["MOCK_ALARMS"] = alarms

    if not updates:
        print("\n⚠️  没有获取到任何更新数据")
        print("   请先配置对应数据源的 URL 环境变量，然后实现 fetch 函数")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] 将更新 {len(updates)} 个数据源: {list(updates.keys())}")
    else:
        update_mock_data_file(updates)
        print(f"\n✅ 已更新 {len(updates)} 个数据源")


if __name__ == "__main__":
    main()
