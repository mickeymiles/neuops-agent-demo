#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# 服务器版本存档脚本（在服务器上执行）
# 职责：部署目录外打包代码备份 + 生成版本指纹文件
# 产物：
#   /home/ubuntu/backup/neuops-agent-demo-20260816.tar.gz
#   /home/ubuntu/backup/server-version-20260816.md
# ═══════════════════════════════════════════════════════════
set -euo pipefail

SRC=/home/ubuntu/neuops-agent-demo
BK=/home/ubuntu/backup
STAMP=20260816
PKG="$BK/neuops-agent-demo-$STAMP.tar.gz"
FINGER="$BK/server-version-$STAMP.md"

echo "═══ 服务器版本存档 $STAMP ═══"

# 0. 前置确认
[ -d "$SRC" ] || { echo "❌ $SRC 不存在"; exit 1; }
systemctl is-active neuops-9007 >/dev/null || { echo "❌ neuops-9007 未运行"; exit 1; }

# 1. 创建备份目录（部署目录外，避开 rsync --delete）
mkdir -p "$BK"

# 2. 打包代码（排除运行时数据：db/chroma/uploads/缓存/历史部署备份/CI）
echo "── 打包 $PKG"
tar -czf "$PKG" -C /home/ubuntu \
  --exclude='chroma_data' \
  --exclude='uploads' \
  --exclude='*.db' \
  --exclude='*.db-*' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='backup_deploy_*' \
  --exclude='.github' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='node_modules' \
  neuops-agent-demo

PKG_SHA=$(sha256sum "$PKG" | awk '{print $1}')
echo "  包 sha256: $PKG_SHA"

# 3. 生成版本指纹文件
echo "── 生成指纹 $FINGER"
HEALTH=$(curl -fsS -m 5 http://127.0.0.1:9007/api/ops/overview || echo '{"ok":false,"error":"health check failed"}')
{
  echo "# NeuOps 服务器版本存档指纹 $STAMP"
  echo
  echo "生成时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "部署目录: $SRC"
  echo "本地 git tag: v1.0-pre-dsh (HEAD=e133c525eaa8ae50937e84040fe2084d697ce4fb)"
  echo
  echo "## 1. systemd 服务状态 neuops-9007"
  echo '```'
  systemctl show neuops-9007 -p ActiveState,SubState,MainPID,ExecStart --no-pager
  echo '```'
  echo
  echo "## 2. 健康检查输出 GET http://127.0.0.1:9007/api/ops/overview"
  echo '```json'
  echo "$HEALTH"
  echo '```'
  echo
  echo "## 3. requirements.txt 全文"
  echo '```'
  cat "$SRC/requirements.txt"
  echo '```'
  echo
  echo "## 4. 关键文件 sha256"
  echo '```'
  ( cd "$SRC" && sha256sum \
      main.py mcp_gateway.py mock_data.py seed_data.py requirements.txt \
      Dockerfile docker-compose.yml .gitignore README.md \
      app/*.py scripts/*.sh static/index.html 2>/dev/null ) | sort -k2
  echo '```'
  echo
  echo "## 5. 生产数据说明（不随代码备份，回退时保留）"
  echo '```'
  ls -la "$SRC"/neuops_sessions.db "$SRC"/chroma_data "$SRC"/uploads 2>/dev/null || true
  echo '```'
  echo
  echo "## 6. 备份包校验"
  echo "备份包路径: $PKG"
  echo "备份包大小: $(stat -c%s "$PKG") bytes"
  echo "备份包 sha256: $PKG_SHA"
  echo
  echo "## 7. 文件清单（备份包内）"
  tar -tzf "$PKG" > /tmp/pkg_list_$$.txt
  echo '```'
  head -60 /tmp/pkg_list_$$.txt
  echo "... (共 $(wc -l < /tmp/pkg_list_$$.txt | tr -d ' ') 个条目)"
  echo '```'
  rm -f /tmp/pkg_list_$$.txt
} > "$FINGER"

echo "✅ 存档完成"
echo "  PKG    = $PKG ($(stat -c%s "$PKG") bytes)"
echo "  FINGER = $FINGER"
echo "  SHA256 = $PKG_SHA"
