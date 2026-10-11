# 生产部署指南

面向内网试点或私有化上线的 Docker Compose 生产栈。开发演示请继续使用根目录 `docker-compose.yml` + `scripts/setup.sh`。

## 与开发栈差异

| 项 | 开发 `docker-compose.yml` | 生产 `docker-compose.prod.yml` |
|---|---|---|
| 后端 | `uvicorn --reload` | `gunicorn` + uvicorn workers |
| 前端 | Vite dev server | 多阶段 `vite build`，Nginx 托管静态文件 |
| Seed | 启动时自动 seed | **不**自动 seed；需显式 `--seed` |
| 端口 | DB/Redis/MinIO 等映射到宿主机 | 仅 Nginx `80`/`443` 对外 |
| API 文档 | `/docs` 可用 | `APP_ENV=production` 时关闭 |
| TLS | 无 | 可选：挂载 `certs/*.pem` |

## 快速开始

```bash
# 1) 生成 .env.prod（首次会随机化密钥）
./scripts/deploy-prod.sh
# Windows: .\scripts\deploy-prod.ps1

# 2) 编辑 .env.prod，填入各场景 LLM API Key，确认 POSTGRES/MinIO 密码

# 3) 再次启动（若第 1 步因缺 Key 已退出，直接再跑即可）
./scripts/deploy-prod.sh

# 可选：写入演示账号（仅内网试点）
./scripts/deploy-prod.sh --seed

# 可选：Prometheus + Grafana（不对宿主机暴露端口，需 docker exec / 临时改 compose）
./scripts/deploy-prod.sh --monitoring
```

访问：`http://<主机>:80`（或 `HTTP_PORT`）。

## 启用 HTTPS（方案 2）

1. 将证书放入仓库根目录 `certs/`：
   - `fullchain.pem`
   - `privkey.pem`
2. 重建 Nginx：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate nginx
```

容器启动时若检测到证书，自动切换 `nginx.prod.ssl.conf`（80→443 跳转 + HSTS）。

同时把 `.env.prod` 中 `CORS_ORIGINS` 改为你的 `https://` 源。

## 首次账号

生产默认**不**创建用户。可选：

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps backend python scripts/seed.py
```

seed 会创建 README 中的演示账号；**务必立即修改密码**，勿对公网暴露。

## 常用运维

```bash
# 日志
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f backend

# 迁移（backend 启动已自动 alembic upgrade head；也可手动）
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm backend alembic upgrade head

# 停止（保留数据卷）
./scripts/deploy-prod.sh --down

# 备份 Postgres 示例
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec -T postgres pg_dump -U finance finance > backup-$(date +%F).sql
```

## 安全清单（上线前）

- [ ] `.env.prod` 中无 `REPLACE_WITH_*` 占位符
- [ ] JWT / ENCRYPTION_KEY / DB / MinIO 均为强随机值
- [ ] 已填 LLM Key；未使用的搜索/OCR 可保持空
- [ ] 未对公网映射 5432/6379/9000/19530
- [ ] 公网或跨网访问已配置 TLS 证书
- [ ] 未使用 seed 默认口令，或已全部改密
- [ ] 防火墙仅放行 80/443

## 相关文件

- `docker-compose.prod.yml`
- `backend/Dockerfile.prod`
- `nginx/Dockerfile.prod` / `nginx.prod.conf` / `nginx.prod.ssl.conf`
- `.env.prod.example`
- `scripts/deploy-prod.sh` / `scripts/deploy-prod.ps1`
