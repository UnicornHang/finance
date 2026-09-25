#!/usr/bin/env bash
# 在 Ubuntu 虚拟机「内部」执行：拉起 finance 后端服务
#
# 用法（在虚拟机里）：
#   bash scripts/deploy-vm.sh          # 后端核心：postgres + redis + minio + backend + celery
#   bash scripts/deploy-vm.sh --all    # 全套：再加 frontend + nginx + prometheus + grafana
#
# 幂等：可反复执行。代码已存在则 git pull，.env 已存在则不覆盖。

set -euo pipefail

REPO="${REPO:-git@github.com:UnicornHang/finance.git}"
BRANCH="${BRANCH:-main}"
DIR="${DIR:-$HOME/finance}"
MODE="${1:-core}"

echo "🚀 finance 后端服务部署（目标目录 $DIR）"
echo ""

# ---------- 1. Docker ----------
echo "==> [1/5] 检查 Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ 未检测到 docker，请先安装：sudo apt install -y docker.io docker-compose-v2"
  exit 1
fi
if ! sudo docker compose version >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
  echo "❌ 未检测到 docker compose v2"
  exit 1
fi
DC="docker compose"
docker compose version >/dev/null 2>&1 || DC="sudo docker compose"
echo "    $(docker --version) / $($DC version --short 2>/dev/null || echo compose-ok)"

# ---------- 2. 代码 ----------
echo "==> [2/5] 准备代码"
if [ -d "$DIR/.git" ]; then
  echo "    目录已存在，拉取最新代码..."
  git -C "$DIR" pull --ff-only
elif [ -d "$DIR" ]; then
  echo "⚠️  $DIR 已存在但不是 git 仓库，跳过拉取"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "    安装 git..."
    sudo apt-get update -qq && sudo apt-get install -y -qq git
  fi
  git clone -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"
echo "    当前提交：$(git log --oneline -1)"

# ---------- 3. .env ----------
echo "==> [3/5] 准备 .env"
if [ ! -f .env ]; then
  cp .env.example .env
  JWT="$(openssl rand -hex 32)"
  ENC="$(openssl rand -base64 32)"
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT|" .env
  sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$ENC|" .env
  echo "    已生成 .env，JWT 与加密密钥已随机化"
  echo "    ⚠️ 记得手动填 LLM_*_API_KEY / TENCENT_OCR_SECRET_*"
else
  echo "    .env 已存在，保留原配置"
fi
# 容器内必须用服务名，防止误填 localhost 导致后端连不上库
grep -qE '^POSTGRES_HOST=(postgres|localhost)' .env || echo "    ⚠️ 检查 POSTGRES_HOST 是否为 postgres"

# ---------- 4. 构建启动 ----------
echo "==> [4/5] 构建并启动容器（首次构建约 10-20 分钟）"
if [ "$MODE" = "--all" ]; then
  $DC up -d --build
else
  $DC up -d --build backend celery-worker
fi

# ---------- 5. 等待就绪 ----------
echo "==> [5/5] 等待服务健康检查"
for i in $(seq 1 90); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "✅ 后端已就绪（耗时约 $((i*2))s）"
    break
  fi
  if [ "$i" = 90 ]; then
    echo "⚠️  后端仍未就绪，看日志：cd $DIR && $DC logs --tail=100 backend"
  fi
  sleep 2
done

VM_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "✨ 完成"
echo "   - API 健康检查：http://$VM_IP:8000/health"
echo "   - Swagger：    http://$VM_IP:8000/docs"
echo "   - MinIO 控制台：http://$VM_IP:9001"
if [ "$MODE" = "--all" ]; then
  echo "   - 平台入口：    http://$VM_IP  （nginx 80）"
  echo "   - 前端直连：    http://$VM_IP:5173"
fi
echo ""
echo "📜 常用："
echo "   - 看日志：cd $DIR && $DC logs -f backend"
echo "   - 看状态：$DC ps"
echo "   - 停服务：$DC down"
