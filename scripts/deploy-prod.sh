#!/usr/bin/env bash
# 生产环境一键部署（Docker Compose prod）
#
# 用法（仓库根目录）：
#   ./scripts/deploy-prod.sh              # 构建并启动
#   ./scripts/deploy-prod.sh --seed       # 启动后跑演示账号 seed（仅内网试点）
#   ./scripts/deploy-prod.sh --monitoring # 额外启动 Prometheus / Grafana
#   ./scripts/deploy-prod.sh --down       # 停止并移除容器（保留 volumes）
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)
DO_SEED=0
DO_MONITORING=0
DO_DOWN=0

for arg in "$@"; do
  case "$arg" in
    --seed) DO_SEED=1 ;;
    --monitoring) DO_MONITORING=1 ;;
    --down) DO_DOWN=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "未知参数: $arg"
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "未检测到 docker，请先安装 Docker / Compose v2"
  exit 1
fi

if [ "$DO_DOWN" -eq 1 ]; then
  echo "==> 停止生产栈"
  "${COMPOSE[@]}" --profile monitoring down
  exit 0
fi

# ---------- .env.prod ----------
if [ ! -f .env.prod ]; then
  echo "==> 从 .env.prod.example 生成 .env.prod 并随机化密钥"
  cp .env.prod.example .env.prod

  if command -v openssl >/dev/null 2>&1; then
    JWT="$(openssl rand -hex 32)"
    ENC="$(openssl rand -base64 32 | tr -d '\n')"
    DB_PASS="$(openssl rand -base64 24 | tr -d '\n=/+' | cut -c1-24)"
    MINIO_PASS="$(openssl rand -base64 24 | tr -d '\n=/+' | cut -c1-24)"
    KMS_B64="$(openssl rand -base64 32 | tr -d '\n')"
    GRAFANA_PASS="$(openssl rand -base64 18 | tr -d '\n=/+' | cut -c1-18)"
    MILVUS_MINIO_PASS="$(openssl rand -base64 18 | tr -d '\n=/+' | cut -c1-18)"
  else
    echo "需要 openssl 以生成随机密钥"
    exit 1
  fi

  # 跨平台 sed：优先 GNU sed，否则用临时文件
  _set_env() {
    local key="$1" val="$2"
    if sed --version >/dev/null 2>&1; then
      sed -i "s|^${key}=.*|${key}=${val}|" .env.prod
    else
      sed -i.bak "s|^${key}=.*|${key}=${val}|" .env.prod
      rm -f .env.prod.bak
    fi
  }

  _set_env JWT_SECRET "$JWT"
  _set_env ENCRYPTION_KEY "$ENC"
  _set_env POSTGRES_PASSWORD "$DB_PASS"
  _set_env DATABASE_URL "postgresql+asyncpg://finance:${DB_PASS}@postgres:5432/finance"
  _set_env MINIO_ROOT_PASSWORD "$MINIO_PASS"
  _set_env MINIO_KMS_SECRET_KEY "finance-prod:${KMS_B64}"
  _set_env GRAFANA_ADMIN_PASSWORD "$GRAFANA_PASS"
  _set_env MILVUS_MINIO_ACCESS_KEY "milvusminio"
  _set_env MILVUS_MINIO_SECRET_KEY "$MILVUS_MINIO_PASS"

  echo "    已写入随机 JWT / DB / MinIO / Grafana 密钥"
  echo ""
  echo "下一步：编辑 .env.prod，填入 LLM_*_API_KEY（及对外 CORS_ORIGINS），然后再次执行："
  echo "  ./scripts/deploy-prod.sh"
  exit 0
fi

# 弱占位符检查（首次生成后的残留）
if grep -qE 'REPLACE_WITH_|please-change' .env.prod; then
  echo "错误: .env.prod 仍含 REPLACE_WITH_* / please-change 占位符，请改完后再部署"
  exit 1
fi

if grep -qE '^LLM_CHITCHAT_API_KEY=$|^LLM_CHITCHAT_API_KEY=\s*$' .env.prod; then
  echo "警告: LLM_CHITCHAT_API_KEY 为空，对话可能失败（可稍后在管理端配置）"
fi

# 供健康检查读取端口
# shellcheck disable=SC1091
set -a
# 只导出需要的端口变量，避免把整份 .env 注入当前 shell 的复杂值弄坏
HTTP_PORT="$(grep -E '^HTTP_PORT=' .env.prod | cut -d= -f2- || true)"
HTTP_PORT="${HTTP_PORT:-80}"
set +a

PROFILE_ARGS=()
if [ "$DO_MONITORING" -eq 1 ]; then
  PROFILE_ARGS=(--profile monitoring)
fi

echo "==> 构建并启动生产栈"
"${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d --build

echo "==> 等待 Nginx / 后端就绪"
ok=0
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:${HTTP_PORT:-80}/nginx-health" >/dev/null 2>&1 \
     || curl -sf "http://127.0.0.1:${HTTP_PORT:-80}/health" >/dev/null 2>&1; then
    echo "服务已就绪（约 $((i * 2))s）"
    ok=1
    break
  fi
  sleep 2
done

if [ "$ok" -ne 1 ]; then
  echo "等待超时，请检查: docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=100"
  exit 1
fi

if [ "$DO_SEED" -eq 1 ]; then
  echo "==> 执行 seed（演示账号，仅建议内网试点）"
  "${COMPOSE[@]}" run --rm --no-deps backend python scripts/seed.py
  echo "    默认账号见 README；上线前请立即修改密码"
fi

echo ""
echo "生产入口: http://localhost:${HTTP_PORT:-80}"
if [ -f certs/fullchain.pem ] && [ -f certs/privkey.pem ]; then
  echo "已检测到 TLS 证书，HTTPS: https://localhost:${HTTPS_PORT:-443}"
fi
echo "日志: docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f"
echo "说明: docs/deploy-production.md"
