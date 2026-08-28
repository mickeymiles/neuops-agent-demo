#!/usr/bin/env bash
# ═══════════════════════════════════════════
# 服务器端部署执行脚本（GitHub Actions CD 调用）
# 职责：安装依赖 → 重启 systemd 服务 → 健康检查
# 用法：在服务器部署目录内执行  bash scripts/remote_deploy.sh
# ═══════════════════════════════════════════
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-9007}"
SERVICE="${SERVICE:-neuops-9007}"
# 服务实际使用的 venv（systemd ExecStart 指向 recon venv）
PYTHON_BIN="${PYTHON_BIN:-/home/ubuntu/recon/.venv/bin/python3}"

echo "═══ 远端部署 $DEPLOY_DIR ═══"

# 1. 若配置了邮件/飞书 secrets，则合并写入服务器 .env（幂等，增量覆盖）
#    值来自 GitHub Actions secrets（DEPLOY_PROC_MAIL_* 等），不落仓库。
ENV_FILE="$DEPLOY_DIR/.env"
: > "$ENV_FILE.tmp"
if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" "$ENV_FILE.tmp"
fi
# 逐 key 覆盖（新值优先）
_put_env() {
  local k="$1"; local v="${2:-}"
  if [ -z "$k" ]; then return; fi
  # 移除已存在的该行，再追加新值
  grep -v "^$k=" "$ENV_FILE.tmp" > "$ENV_FILE.tmp2" 2>/dev/null || true
  mv "$ENV_FILE.tmp2" "$ENV_FILE.tmp"
  printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE.tmp"
}
_put_env "PROC_MAIL_USERNAME" "${DEPLOY_PROC_MAIL_USERNAME:-}"
_put_env "PROC_MAIL_PASSWORD" "${DEPLOY_PROC_MAIL_PASSWORD:-}"
_put_env "PROC_FEISHU_APP_ID" "${DEPLOY_PROC_FEISHU_APP_ID:-}"
_put_env "PROC_FEISHU_APP_SECRET" "${DEPLOY_PROC_FEISHU_APP_SECRET:-}"
_put_env "PROC_FEISHU_PM_OPEN_ID" "${DEPLOY_PROC_FEISHU_PM_OPEN_ID:-}"
_put_env "PROC_FEISHU_BITABLE_APP_TOKEN" "${DEPLOY_PROC_FEISHU_BITABLE_APP_TOKEN:-}"
_put_env "PROC_FEISHU_BITABLE_TASK_TABLE_ID" "${DEPLOY_PROC_FEISHU_BITABLE_TASK_TABLE_ID:-}"
_put_env "PROC_FEISHU_BITABLE_LEDGER_TABLE_ID" "${DEPLOY_PROC_FEISHU_BITABLE_LEDGER_TABLE_ID:-}"
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# 2. 安装依赖（用服务实际 venv）
"$PYTHON_BIN" -m pip install -r "$DEPLOY_DIR/requirements.txt"

# 3. 重启 systemd 服务
sudo systemctl restart "$SERVICE"
sleep 2

# 4. 健康检查
echo "═══ 健康检查 http://127.0.0.1:$PORT/api/ops/overview ═══"
for i in $(seq 1 20); do
  if curl -fsS -m 3 "http://127.0.0.1:$PORT/api/ops/overview" >/dev/null 2>&1; then
    echo "✅ 服务健康 (${i}x3s)"
    exit 0
  fi
  sleep 3
done

echo "❌ 健康检查超时，部署失败" >&2
exit 1
