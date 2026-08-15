#!/usr/bin/env bash
# ═══════════════════════════════════════════
# 服务器部署脚本（Harness CD 与手动部署共用）
# 用法：
#   ./scripts/deploy.sh [SERVER_USER@SERVER_HOST] [/path/to/deploy]
# 示例：
#   ./scripts/deploy.sh ubuntu@1.2.3.4 /home/ubuntu/neuops-agent-demo
# ═══════════════════════════════════════════
set -euo pipefail

TARGET="${1:-${DEPLOY_TARGET:-}}"
DEPLOY_DIR="${2:-${DEPLOY_DIR:-/home/ubuntu/neuops-agent-demo}}"
PORT="${PORT:-9007}"

if [ -z "$TARGET" ]; then
  echo "❌ 用法: $0 [user@host] [/path/to/deploy]" >&2
  exit 1
fi

echo "═══ 部署 NeuOps 到 $TARGET:$DEPLOY_DIR ═══"

# 1. 同步代码（rsync 排除运行时数据）
rsync -az --delete \
  --exclude='.git' --exclude='.github' \
  --exclude='chroma_data' --exclude='uploads' \
  --exclude='*.db' --exclude='__pycache__' --exclude='.venv' --exclude='*.log' \
  -e ssh ./ "$TARGET:$DEPLOY_DIR/"

# 2. 安装依赖
ssh "$TARGET" "cd $DEPLOY_DIR && pip3 install -r requirements.txt 2>/dev/null || pip3 install --user -r requirements.txt"

# 3. 重启服务（systemd 或直接 nohup）
ssh "$TARGET" "cd $DEPLOY_DIR && (systemctl --user restart neuops 2>/dev/null || \
  sudo systemctl restart neuops 2>/dev/null || \
  (pkill -f 'uvicorn main:app' 2>/dev/null || true; sleep 1; \
   nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT > /tmp/neuops.log 2>&1 &) || true)"

# 4. 健康检查（等待启动）
echo "═══ 健康检查 http://$TARGET:$PORT/api/ops/overview ═══"
for i in $(seq 1 20); do
  if curl -fsS -m 3 "http://$TARGET:$PORT/api/ops/overview" >/dev/null 2>&1; then
    echo "✅ 部署成功，服务健康 (${i}x3s)"
    exit 0
  fi
  sleep 3
done

echo "❌ 健康检查超时，部署失败（可触发自动回滚）" >&2
exit 1
