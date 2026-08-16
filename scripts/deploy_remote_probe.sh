#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 远程探针部署脚本
# 把统一监控探针模块部署到目标服务器，注册 systemd 服务持续采集并上报监控中心。
# 与监控中心相同的采集逻辑（服务器/容器/数据库/中间件/应用/网络 + 日志），
# 上报后数据按主机名隔离存入监控中心，实体自动出现在监控页面并参与告警。
#
# 用法:
#   ./scripts/deploy_remote_probe.sh ubuntu@49.234.48.117
#
# 环境变量:
#   CENTER_URL        上报地址（默认 http://122.51.98.98:9007/api/ops/probe/ingest）
#   PROBE_INTERVAL    采集周期秒（默认 30）
#   REMOTE_PROBE_DIR  远程部署目录（默认 /home/ubuntu/neuops-remote-probe）
#   REMOTE_PROBE_TARGET  默认目标（可用环境变量代替参数）
# ─────────────────────────────────────────────────────────────
set -euo pipefail

TARGET="${1:-${REMOTE_PROBE_TARGET:-}}"
CENTER_URL="${CENTER_URL:-http://122.51.98.98:9007/api/ops/probe/ingest}"
DEPLOY_DIR="${REMOTE_PROBE_DIR:-/home/ubuntu/neuops-remote-probe}"
INTERVAL="${PROBE_INTERVAL:-30}"
SERVICE="neuops-remote-probe"

if [ -z "$TARGET" ]; then
  echo "用法: $0 [user@host]   （如: $0 ubuntu@49.234.48.117）"
  echo "环境变量: CENTER_URL / PROBE_INTERVAL / REMOTE_PROBE_DIR / REMOTE_PROBE_TARGET / SSHPASS"
  exit 1
fi

# 密码认证支持：设置 SSHPASS 环境变量时，内部 ssh/rsync 走 sshpass -e（密码不出现在命令行）
SSH_CMD="ssh"
RSYNC_SSH="ssh"
if [ -n "${SSHPASS:-}" ]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "已设置 SSHPASS 但本机缺少 sshpass，请先安装（如: brew install hudochenkov/sshpass/sshpass）" >&2
    exit 1
  fi
  SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=accept-new"
  RSYNC_SSH="sshpass -e ssh -o StrictHostKeyChecking=accept-new"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "═══ 部署远程探针 → $TARGET"
echo "    部署目录: $DEPLOY_DIR"
echo "    上报地址: $CENTER_URL"
echo "    采集周期: ${INTERVAL}s"

# 1. 同步最小探针集（probe 模块 + app 基础模块 + seed_data）
$SSH_CMD "$TARGET" "mkdir -p '$DEPLOY_DIR/app'"
rsync -az --delete -e "$RSYNC_SSH" \
  --exclude='__pycache__' \
  ./app/__init__.py ./app/config.py ./app/db.py \
  "$TARGET:$DEPLOY_DIR/app/"
rsync -az --delete -e "$RSYNC_SSH" \
  --exclude='__pycache__' \
  ./app/probe/ \
  "$TARGET:$DEPLOY_DIR/app/probe/"
rsync -az -e "$RSYNC_SSH" --exclude='__pycache__' ./seed_data.py "$TARGET:$DEPLOY_DIR/"

# 2. 远程安装运行依赖（缺 python3-venv 时用 apt 补齐并重建 venv，避免 venv 无 pip）
$SSH_CMD "$TARGET" "bash -s" <<EOF
set -euo pipefail
if [ ! -x "$DEPLOY_DIR/venv/bin/python3" ]; then
  python3 -m venv "$DEPLOY_DIR/venv" 2>/dev/null || {
    echo "[i] 安装 python3-venv ..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv
    python3 -m venv "$DEPLOY_DIR/venv"
  }
fi
if [ ! -x "$DEPLOY_DIR/venv/bin/pip" ]; then
  "$DEPLOY_DIR/venv/bin/python3" -m ensurepip --upgrade 2>/dev/null || {
    echo "[i] venv 缺 pip，重建 venv ..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv
    rm -rf "$DEPLOY_DIR/venv"
    python3 -m venv "$DEPLOY_DIR/venv"
  }
fi
"$DEPLOY_DIR/venv/bin/pip" install --quiet --upgrade pip
"$DEPLOY_DIR/venv/bin/pip" install --quiet psutil
EOF

# 3. 注册 systemd 服务并启动（unit 用 printf 生成，避免嵌套 heredoc）
$SSH_CMD "$TARGET" "bash -s" <<EOF
set -euo pipefail
printf '%s\n' \
  '[Unit]' \
  'Description=NeuOps Remote Probe (collect & report to monitor center)' \
  'After=network-online.target' \
  'Wants=network-online.target' \
  '' \
  '[Service]' \
  'Type=simple' \
  'WorkingDirectory=$DEPLOY_DIR' \
  'ExecStart=$DEPLOY_DIR/venv/bin/python3 -m app.probe.cli --loop --interval $INTERVAL --report-http $CENTER_URL' \
  'Restart=always' \
  'RestartSec=10' \
  '' \
  '[Install]' \
  'WantedBy=multi-user.target' \
  > /tmp/$SERVICE.service
sudo mv /tmp/$SERVICE.service /etc/systemd/system/$SERVICE.service
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE
sudo systemctl restart $SERVICE
sleep 3
echo "---- systemd 状态 ----"
systemctl --no-pager status $SERVICE | head -n 15
EOF

echo "✅ 远程探针部署完成"
echo "   机器: $TARGET ($DEPLOY_DIR)"
echo "   上报: $CENTER_URL"
echo "   验证: 打开 http://122.51.98.98:9007/ops 实体页，应出现该服务器实体"
echo "   日志: ssh $TARGET 'journalctl -u $SERVICE -f'"
