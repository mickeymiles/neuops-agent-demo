#!/usr/bin/env bash
# ═══════════════════════════════════════════
# 服务器部署脚本（本地手动部署；GitHub Actions CD 等价走 ci.yml deploy job）
# 用法：
#   ./scripts/deploy.sh [SERVER_USER@SERVER_HOST] [/path/to/deploy]
# 示例：
#   ./scripts/deploy.sh ubuntu@1.2.3.4 /home/ubuntu/neuops-agent-demo
# ═══════════════════════════════════════════
set -euo pipefail

TARGET="${1:-${DEPLOY_TARGET:-}}"
DEPLOY_DIR="${2:-${DEPLOY_DIR:-/home/ubuntu/neuops-agent-demo}}"
PORT="${PORT:-9007}"
SERVICE="${SERVICE:-neuops-9007}"

if [ -z "$TARGET" ]; then
  echo "❌ 用法: $0 [user@host] [/path/to/deploy]" >&2
  exit 1
fi

echo "═══ 部署 NeuOps 到 $TARGET:$DEPLOY_DIR（服务 $SERVICE）═══"

# 1. 同步代码（rsync 排除运行时数据与备份目录）
rsync -az --delete \
  --exclude='.git' --exclude='.github' \
  --exclude='chroma_data' --exclude='uploads' \
  --exclude='*.db' --exclude='__pycache__' \
  --exclude='.venv' --exclude='venv' \
  --exclude='*.log' --exclude='backup_deploy_*' --exclude='.pytest_cache' \
  -e ssh ./ "$TARGET:$DEPLOY_DIR/"

# 2. 远端安装依赖 + 重启 + 健康检查（复用 CD 同一执行脚本）
ssh "$TARGET" "cd $DEPLOY_DIR && bash scripts/remote_deploy.sh"
