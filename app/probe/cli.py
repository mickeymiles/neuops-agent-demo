# -*- coding: utf-8 -*-
"""统一探针独立 CLI

支持：
- 单轮采集并落库：        python -m app.probe.cli --once
- 持续采集（后台循环）：  python -m app.probe.cli --loop --interval 30
- 采集后打印 JSON：       python -m app.probe.cli --once --json
- HTTP 上报到监控中心：  python -m app.probe.cli --loop --report-http http://127.0.0.1:9007/api/ops/probe/ingest

远程探针部署：将本模块拷贝/安装到目标机，配置 --report-http 指向监控中心即可上报。
"""
import argparse
import json
import sys
import time
import urllib.request

from .manager import ProbeManager


def _report_http(url: str, payload: dict) -> str:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="neuops-probe", description="统一监控探针")
    parser.add_argument("--once", action="store_true", help="只执行一轮采集")
    parser.add_argument("--loop", action="store_true", help="持续采集")
    parser.add_argument("--interval", type=int, default=30, help="采集周期（秒），默认 30")
    parser.add_argument("--json", action="store_true", help="采集后打印 JSON 结果")
    parser.add_argument("--report-http", default="", help="采集后通过 HTTP POST 上报到监控中心")
    args = parser.parse_args(argv)

    pm = ProbeManager(interval=args.interval)
    if args.once or (not args.loop):
        summary = pm.run_once()
        print(f"[probe] round done: {json.dumps(summary, ensure_ascii=False)}", file=sys.stderr)
        if args.json:
            print(pm.dump_json())
        if args.report_http:
            print(_report_http(args.report_http, pm.to_payload()))
        return 0

    # loop 模式
    print(f"[probe] start loop, interval={args.interval}s", file=sys.stderr)
    try:
        while True:
            summary = pm.run_once()
            print(f"[probe] {pm.last_run_at} {json.dumps(summary, ensure_ascii=False)}",
                  file=sys.stderr)
            if args.json:
                print(pm.dump_json())
            if args.report_http:
                try:
                    print(_report_http(args.report_http, pm.to_payload()))
                except Exception as e:  # noqa: BLE001
                    print(f"[probe] report error: {e}", file=sys.stderr)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("[probe] stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
