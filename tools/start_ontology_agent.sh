#!/usr/bin/env bash
# 本体轨数字员工（采购智能体）常驻启动脚本
# 目标：让智能体在服务器后台持续运行，并自动按扫描水位认领/执行询价流程。
#
# 前置：
#   1. 仓库已 git pull 到最新（含本文件）
#   2. 仓库根目录存在 .env（gitignored，切勿提交），且包含：
#        ONT_MAIL_USERNAME=biquanzhi4@163.com
#        ONT_MAIL_PASSWORD=<b4 授权码>
#        ONT_SUPPLIERS=中软国际:biquanzhi2@163.com,神州数码:biquanzhi6@163.com
#        ONT_APPROVERS=biquanzhi5@163.com
#        ONT_REQUESTERS=biquanzhi1@163.com   # 后续可加 2 个真实业务邮箱，逗号分隔
#        ONT_MODE=ontology
#        ONT_EXEC=1
#        ONT_SCHEDULER=1                      # 常驻自动执行的关键开关
#      （b1/b2/b5/b6 的口令只用于"模拟人"的冒烟脚本，生产常驻无需它们）
#   3. 已建好虚拟环境：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#
# 用法：
#   bash tools/start_ontology_agent.sh
# 停止：
#   kill $(cat logs/ontology_agent.pid)
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)"
# 生产常驻：确保自动执行开关打开（即使 .env 未设也兜底开启）
export ONT_MODE=ontology
export ONT_EXEC=1
export ONT_SCHEDULER=1

mkdir -p logs
echo "[start] 启动本体轨采购智能体（0.0.0.0:9007，scheduler=on）..."
nohup .venv/bin/python main.py > logs/ontology_agent.log 2>&1 &
echo $! > logs/ontology_agent.pid
echo "[start] pid=$(cat logs/ontology_agent.pid) 日志=logs/ontology_agent.log"

sleep 4
if curl -s -m 5 http://127.0.0.1:9007/api/ontology-emp009/claim-state >/dev/null 2>&1; then
  echo "[ok] 服务已就绪，claim-state 可访问"
else
  echo "[warn] 服务尚未就绪，请查看 logs/ontology_agent.log"
fi
