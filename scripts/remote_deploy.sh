#!/usr/bin/env bash
# ═══════════════════════════════════════════
# 服务器端部署执行脚本（GitHub Actions CD / 手动 deploy.sh 调用）
# 职责：确保 venv → 安装依赖 → 合并 .env（含本体轨 ONT_*）→
#       安装并重启 systemd 服务 → 健康检查
# 用法：在服务器部署目录内执行  bash scripts/remote_deploy.sh
# ═══════════════════════════════════════════
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-9007}"
SERVICE="${SERVICE:-neuops-9007}"
# venv 放在部署目录内（rsync 已排除 .venv，首次需自建）
PYTHON_BIN="${PYTHON_BIN:-$DEPLOY_DIR/.venv/bin/python3}"

echo "═══ 远端部署 $DEPLOY_DIR (端口 $PORT / 服务 $SERVICE) ═══"

# 0. 确保 venv 存在（修复：原硬编码 /home/ubuntu/recon/.venv 在 neuops-agent-demo 部署目录不存在）
if [ ! -x "$PYTHON_BIN" ]; then
  echo "── 创建 venv：$DEPLOY_DIR/.venv"
  python3 -m venv "$DEPLOY_DIR/.venv"
fi
PYTHON_BIN="$DEPLOY_DIR/.venv/bin/python3"

# 1. 种子化 .env（首次部署从 .env.example 生成，避免丢失本体轨 ONT_* 配置）
ENV_FILE="$DEPLOY_DIR/.env"
if [ ! -f "$ENV_FILE" ] && [ -f "$DEPLOY_DIR/.env.example" ]; then
  echo "── 从 .env.example 种子化 .env"
  cp "$DEPLOY_DIR/.env.example" "$ENV_FILE"
fi
: > "$ENV_FILE.tmp"
[ -f "$ENV_FILE" ] && cp "$ENV_FILE" "$ENV_FILE.tmp"

_put_env() {
  local k="$1"; local v="${2:-}"
  [ -z "$k" ] && return
  grep -v "^$k=" "$ENV_FILE.tmp" > "$ENV_FILE.tmp2" 2>/dev/null || true
  mv "$ENV_FILE.tmp2" "$ENV_FILE.tmp"
  printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE.tmp"
}

# 本体轨数据库路径必须指向服务器部署目录（覆盖本地 macOS 默认 /Users/...）
_put_env "ONT_DB_PATH" "$DEPLOY_DIR/neuops_ontology.db"

# 敏感凭据从 CI secrets 注入（不落仓库）
_put_env "PROC_MAIL_USERNAME" "${DEPLOY_PROC_MAIL_USERNAME:-}"
_put_env "PROC_MAIL_PASSWORD" "${DEPLOY_PROC_MAIL_PASSWORD:-}"
_put_env "PROC_FEISHU_APP_ID" "${DEPLOY_PROC_FEISHU_APP_ID:-}"
_put_env "PROC_FEISHU_APP_SECRET" "${DEPLOY_PROC_FEISHU_APP_SECRET:-}"
_put_env "PROC_FEISHU_PM_OPEN_ID" "${DEPLOY_PROC_FEISHU_PM_OPEN_ID:-}"
_put_env "PROC_FEISHU_BITABLE_APP_TOKEN" "${DEPLOY_PROC_FEISHU_BITABLE_APP_TOKEN:-}"
_put_env "PROC_FEISHU_BITABLE_TASK_TABLE_ID" "${DEPLOY_PROC_FEISHU_BITABLE_TASK_TABLE_ID:-}"
_put_env "PROC_FEISHU_BITABLE_LEDGER_TABLE_ID" "${DEPLOY_PROC_FEISHU_BITABLE_LEDGER_TABLE_ID:-}"

# 本体轨采购智能体(b4) 口令（CI: DEPLOY_ONT_MAIL_PASSWORD）
_put_env "ONT_MAIL_USERNAME" "${DEPLOY_ONT_MAIL_USERNAME:-biquanzhi4@163.com}"
_put_env "ONT_MAIL_PASSWORD" "${DEPLOY_ONT_MAIL_PASSWORD:-}"

# 非敏感 ONT 配置若缺失则从 .env.example 继承
for k in ONT_MAIL_DISPLAY_NAME ONT_SUPPLIERS ONT_APPROVERS ONT_REQUESTERS ONT_SCAN_HOURS ONT_MODE ONT_EXEC ONT_SCHEDULER; do
  if ! grep -q "^$k=" "$ENV_FILE.tmp"; then
    val=$(grep "^$k=" "$DEPLOY_DIR/.env.example" 2>/dev/null | tail -1 | cut -d= -f2-)
    [ -n "$val" ] && _put_env "$k" "$val"
  fi
done

mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# 2. 安装依赖
"$PYTHON_BIN" -m pip install --upgrade pip -q
"$PYTHON_BIN" -m pip install -r "$DEPLOY_DIR/requirements.txt" -q

# 3. 安装/更新 systemd 单元（动态写入真实路径，修复 recon 陈旧路径）
UNIT_SRC="$DEPLOY_DIR/tools/neuops-9007.service"
if [ -f "$UNIT_SRC" ]; then
  sudo install -m 0644 "$UNIT_SRC" /etc/systemd/system/neuops-9007.service
  sudo sed -i "s#__DEPLOY_DIR__#$DEPLOY_DIR#g; s#__PYTHON_BIN__#$PYTHON_BIN#g" /etc/systemd/system/neuops-9007.service
  sudo systemctl daemon-reload
  sudo systemctl enable neuops-9007
fi

# 4. 重启服务
sudo systemctl restart "$SERVICE"
sleep 3

# 5. 健康检查
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
