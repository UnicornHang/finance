#!/bin/bash
# 一键初始化脚本
# 用法：./scripts/init.sh

set -e

echo "🚀 Finance AI Agent - 初始化"
echo ""

# 检查环境
if [ ! -f .env ]; then
    echo "❌ .env 文件不存在，正在从 .env.example 复制..."
    cp .env.example .env
    echo "✅ 请编辑 .env 配置密钥后重新运行"
    exit 1
fi

# 启动服务
echo "📦 启动 Docker 服务..."
docker-compose up -d

# 等待数据库就绪
echo "⏳ 等待 PostgreSQL 就绪..."
for i in {1..30}; do
    if docker-compose exec -T postgres pg_isready -U finance > /dev/null 2>&1; then
        echo "✅ 数据库就绪"
        break
    fi
    sleep 2
done

# 运行迁移
echo "🔄 执行数据库迁移..."
docker-compose exec -T backend alembic upgrade head

# 初始化种子数据
echo "🌱 初始化种子数据..."
docker-compose exec -T backend python scripts/seed.py || echo "⚠️  种子数据初始化失败，可手动重试"

echo ""
echo "✨ 初始化完成！"
echo ""
echo "📍 访问地址："
echo "   - 前端：http://localhost:5173"
echo "   - API 文档：http://localhost:8000/docs"
echo "   - MinIO 控制台：http://localhost:9001"
echo ""
echo "🔑 默认账号："
echo "   - admin / Admin@123"
echo "   - finance01 / Finance@123"
echo "   - employee01 / Emp@123"
echo ""