#!/usr/bin/env bash
# ═══════════════════════════════════════════
# GitHub 私有仓库一键推送脚本（预留激活）
#
# 用法（二选一）：
#   A. 自动创建私有仓库（需已安装 gh CLI 并登录）：
#        ./scripts/push_github.sh create [owner]
#   B. 使用已有仓库地址推送：
#        ./scripts/push_github.sh push git@github.com:<owner>/neuops-agent-demo.git
#
# 说明：仓库本地已 init 并完成首次提交（main 分支）。
#       本脚本只负责关联 remote 并推送，不改动任何代码。
# ═══════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_NAME="neuops-agent-demo"
MODE="${1:-push}"
ARG="${2:-}"

if [ "$MODE" = "create" ]; then
  OWNER="${ARG:-$(gh api user --jq .login 2>/dev/null || echo '')}"
  if [ -z "$OWNER" ]; then
    echo "❌ 无法获取 GitHub 用户名，请先安装并登录 gh CLI（brew install gh && gh auth login）" >&2
    exit 1
  fi
  echo "═══ 创建 GitHub 私有仓库 ${OWNER}/${REPO_NAME} ═══"
  gh repo create "$REPO_NAME" --private --source=. --remote=origin --push
  echo "✅ 已创建并推送私有仓库"
elif [ "$MODE" = "push" ]; then
  REMOTE_URL="${ARG:?用法: ./scripts/push_github.sh push <仓库URL>}"
  echo "═══ 推送代码到 ${REMOTE_URL} ═══"
  git remote remove origin 2>/dev/null || true
  git remote add origin "$REMOTE_URL"
  git push -u origin main
  echo "✅ 推送完成"
else
  echo "❌ 未知模式: $MODE（支持 create / push）" >&2
  exit 1
fi

echo ""
echo "────────────────────────────────────────────"
echo " 下一步：GitHub 仓库 → Settings → Secrets 配置"
echo "  - DEEPSEEK_API_KEY（可选，LLM 功能）"
echo "  - 推送后 .github/workflows/ci.yml 自动触发 CI"
echo "  - Harness 激活见 harness/README.md"
echo "────────────────────────────────────────────"
