#!/usr/bin/env bash
# 一键启动脚本 - 首次运行 / 重置环境都用这个
#
# 用法：
#   ./scripts/setup.sh         # 启动所有服务并初始化种子数据
#   ./scripts/setup.sh --reset # 重置：删除 volumes、重新跑 migration + seed

set -e

# 切到项目根目录
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "🚀 Finance AI Agent - 一键启动"
echo ""

# -------- 1. .env --------
if [ ! -f .env ]; then
  echo "📋 .env 不存在，从 .env.example 复制..."
  cp .env.example .env
  echo "✅ 已生成 .env（如需修改 JWT_SECRET / LLM Key 等，请编辑 .env）"
else
  echo "✅ .env 已存在"
fi

# -------- 2. Docker Compose --------
if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
  echo "❌ 未检测到 docker / docker-compose，请先安装 Docker Desktop"
  exit 1
fi

# 兼容 docker-compose v1 和 v2
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

# -------- 3. 重置选项 --------
if [ "$1" = "--reset" ]; then
  echo ""
  echo "🧹 重置：删除 volumes（postgres / minio / redis 数据）..."
  $DC down -v
fi

# -------- 4. 启动服务 --------
echo ""
echo "📦 启动 Docker 服务..."
$DC up -d --build

# -------- 5. 等待 healthy --------
echo ""
echo "⏳ 等待 PostgreSQL / Redis / MinIO 就绪..."
for i in $(seq 1 60); do
  PG_OK=$($DC exec -T postgres pg_isready -U "${POSTGRES_USER:-finance}" 2>/dev/null && echo 1 || echo 0)
  REDIS_OK=$($DC exec -T redis redis-cli ping 2>/dev/null | grep -q PONG && echo 1 || echo 0)
  MINIO_OK=$($DC exec -T minio curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1 && echo 1 || echo 0)
  if [ "$PG_OK" = "1" ] && [ "$REDIS_OK" = "1" ] && [ "$MINIO_OK" = "1" ]; then
    echo "✅ 基础设施就绪（耗时 ${i}s）"
    break
  fi
  sleep 2
done

# -------- 6. 等待 backend healthy --------
echo ""
echo "⏳ 等待后端 API 就绪..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "✅ 后端 API 已就绪（耗时 ${i}s）"
    break
  fi
  sleep 2
done

# -------- 7. 输出访问地址 --------
echo ""
echo "✨ 启动完成！"
echo ""
echo "📍 访问地址（推荐统一通过 nginx 80 端口）："
echo "   - 平台入口：http://localhost"
echo "   - 前端直连（开发）：http://localhost:5173"
echo "   - API 文档：http://localhost/docs"
echo "   - MinIO 控制台：http://localhost:9001"
echo ""
echo "🔑 默认账号（密码见 README）："
echo "   - admin / Admin@123         （管理员）"
echo "   - finance01 / Finance@123   （财务）"
echo "   - employee01 / Emp@123      （员工）"
echo ""
echo "📜 后续操作："
echo "   - 查看日志：$DC logs -f backend"
echo "   - 跑烟测：  ./scripts/smoke.sh"
echo "   - 重置环境：./scripts/setup.sh --reset"
echo ""
