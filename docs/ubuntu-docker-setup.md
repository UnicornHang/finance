# Ubuntu 虚拟机 + Docker 后端环境配置指南
> 本机docker能运行，优先本机docker运行
> 适用：把 `finance` 项目跑在 Ubuntu（VMware / VirtualBox）虚拟机的 Docker 里，从 Windows 宿主机浏览器访问。
> 本文说的是**后端及依赖服务的配置**，Docker Compose 一把梭起全部服务（PG / Redis / MinIO / Backend / Celery / Frontend / Nginx / Prometheus / Grafana）。

---

## 0. 端口地图（先在心里有张图）

| 服务 | 容器名 | 容器内端口 | 映射到 VM 端口 | 说明 |
| --- | --- | --- | --- | --- |
| Nginx | `finance-nginx` | 80 / 443 | 80 / 443 | **统一入口**，反代前端和 `/api/` |
| Frontend | `finance-frontend` | 5173 | 5173 | Vite dev server（调试用） |
| Backend | `finance-backend` | 8000 | 8000 | FastAPI，`/health`、`/docs` |
| Celery Worker | `finance-celery-worker` | - | - | OCR 异步任务 |
| PostgreSQL+pgvector | `finance-postgres` | 5432 | 5432 | 主库 |
| Redis | `finance-redis` | 6379 | 6379 | 缓存 + Celery broker |
| MinIO | `finance-minio` | 9000 / 9001 | 9000 / 9001 | 对象存储 / 控制台 |
| Prometheus | `finance-prometheus` | 9090 | 9090 | 可不启 |
| Grafana | `finance-grafana` | 3000 | 3000 | 可不启 |

**容器之间互相访问一律用服务名**（`postgres` / `redis` / `minio` / `backend`），**不能**写 `localhost`——在容器里 `localhost` 是它自己。

---

## 1. Ubuntu 上的 Docker 前置检查

```bash
docker --version              # 需 24+
docker compose version        # 需 v2（注意是空格不是横线）
docker run hello-world        # 确认能拉镜像

sudo usermod -aG docker $USER # 免 sudo，执行后注销重登录
```

资源建议：**4 核 / 8G 内存 / 60G 磁盘**。首次构建会拉 Python 依赖（langchain、litellm、opentelemetry 等），镜像 + node_modules 大约 4~6G，构建 10~20 分钟。

> 网络：虚拟机建议用**桥接（Bridged）**或 NAT + 端口转发。桥接最简单，VM 有独立局域网 IP，Windows 直接 `http://<VM-IP>` 访问。
> NAT 的话需要在 VMware「虚拟网络编辑器 → NAT 设置」里转发 80、5173、8000、9001。

---

## 2. 把代码弄进虚拟机

### 方式 A：git clone（推荐）

仓库已推送到 GitHub，且 `.gitignore` 已排除 `node_modules/`、`.venv/`、`__pycache__/`、`.env`：

```bash
sudo apt install -y git
git clone git@github.com:UnicornHang/finance.git
cd finance
```

如果远端不是最新的，先在 Windows 上 `git push origin main`。

### 方式 B：scp / rsync 拷贝（仓库不方便拉时）

在 **Windows 的 Git Bash** 里执行，**务必排除 Windows 专属产物**，否则 Linux 上直接崩：

```bash
rsync -avz --delete \
  -e "ssh -p 22" \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude 'backend/.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude 'backend/finance_backend.egg-info/' \
  --exclude 'frontend/dist/' \
  --exclude 'python-3.12.10-amd64.exe' \
  /d/project/finance/ <user>@<VM-IP>:~/finance/
```

排掉的理由：`node_modules` 里有 Windows 原生二进制（`.node`），`backend/.venv` 是 Windows 的 Python 虚拟环境，拷过去**完全不能用**。依赖在容器里重新安装。

---

## 3. 配置 `.env`（核心步骤）

项目根目录已有 `.env`（`.gitignore` 已忽略，不会进仓库）。没有就从模板生成：

```bash
cp .env.example .env
nano .env
```

### 3.1 必须改的（不建议用默认值上环境）

| 变量 | 怎么填 | 生成方式 |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | 数据库密码 | 自定义，改了要**同步改 `DATABASE_URL`** |
| `DATABASE_URL` | `postgresql+asyncpg://finance:<密码>@postgres:5432/finance` | **host 必须是 `postgres`** |
| `JWT_SECRET` | ≥32 位随机串 | `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | base64 32 字节 | `openssl rand -base64 32` |
| `MINIO_ROOT_PASSWORD` | MinIO 控制台密码 | 自定义 |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 密码 | 自定义 |

> ⚠️ `POSTGRES_PASSWORD` 和 `DATABASE_URL` 里那串密码必须一致，改一个忘另一个，后端起来会连不上库。

### 3.2 按你的实际情况填

**LLM（四个场景，可先全用同一个 key）**

```bash
LLM_CHITCHAT_MODEL=gpt-4o-mini
LLM_CHITCHAT_API_KEY=sk-xxxx
LLM_CHITCHAT_BASE_URL=https://api.openai.com/v1   # 走国内中转就换成中转地址
# policy / ocr / contract 同理
```

**Embedding（RAG 向量化，Phase B 才用）**

```bash
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=sk-xxxx
EMBEDDING_DIMENSION=1536     # 换模型时这里的维度要跟着改
```

**OCR（发票识别）**

```bash
OCR_PROVIDER=tencent
TENCENT_OCR_SECRET_ID=AKID...
TENCENT_OCR_SECRET_KEY=xxxx
TENCENT_OCR_REGION=ap-guangzhou
```

留空也不影响启动——代码里有 Mock 降级，会用假数据走完整流程，方便先跑通链路。

### 3.3 不要动的（改了会断）

| 变量 | 值 | 原因 |
| --- | --- | --- |
| `POSTGRES_HOST` | `postgres` | compose 服务名 |
| `REDIS_HOST` | `redis` | 同上 |
| `MINIO_HOST` | `minio` | 同上 |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | worker 容器里没有 localhost 的 redis |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` | 同上 |
| `VITE_API_BASE_URL` | 留空 | 走同源相对路径，由 nginx 统一反代 |
| `VITE_API_PROXY_TARGET` | 留空 | compose 里已强制覆盖为 `http://backend:8000` |

### 3.4 ⚠️ 一个容易踩的坑：`backend/.env`

compose 把 `./backend` 挂载到了容器的 `/app`，所以 **`backend/.env` 会作为 `/app/.env` 进容器**，而 `app/config.py` 的 `Settings` 读的就是相对路径 `.env`。

结果：
- 容器里的**真实环境变量**（来自根目录 `.env`）优先级高于 `.env` 文件，所以目前能正常跑；
- 但 `backend/.env` 里写的是 `POSTGRES_HOST=localhost`，一旦你哪天在虚拟机里直接 `uvicorn app.main:app` 跑，就会连不上容器里的 PG；
- 而且这份文件里带了**真实腾讯云密钥**，别提交上去。

建议：**走 Docker 部署时把 `backend/.env` 删掉或改名备份**，全项目只用根目录那一份 `.env`。

```bash
mv backend/.env backend/.env.win-local.bak
```

---

## 4. 启动

```bash
# 一次性把脚本换行符修成 LF（从 Windows 拷过来的 .sh 是 CRLF，在 Linux 上会报 /bin/bash^M bad interpreter）
sudo apt install -y dos2unix
dos2unix scripts/*.sh
chmod +x scripts/*.sh

# 一键启动：自动分配 .env → 构建 → 拉起服务 → 等待 healthy
./scripts/setup.sh

# 或者手动
docker compose up -d --build
```

后端容器的启动命令已经串好了 `alembic upgrade head` → `python scripts/seed.py` → `uvicorn --reload`，**不需要手动执行迁移**。

首次构建慢属正常。想看进度：`docker compose logs -f --tail=100 backend`。

---

## 5. 验证

```bash
docker compose ps                    # 全部 Up / healthy
curl http://localhost/health         # {"status":"ok",...}
curl http://localhost/api/v1/llm/providers
./scripts/smoke.sh                   # 9 步端到端烟测
```

浏览器访问（`<VM-IP>` 换成虚拟机 IP）：

| 地址 | 用途 |
| --- | --- |
| `http://<VM-IP>` | **平台入口**（推荐，前端+API 同源，无跨域问题） |
| `http://<VM-IP>/docs` | Swagger |
| `http://<VM-IP>:5173` | 前端直连调试 |
| `http://<VM-IP>:9001` | MinIO 控制台 |

默认账号：`admin / Admin@123`、`finance01 / Finance@123`、`employee01 / Emp@123`（首次登录强制改密）。

> 如果直接从 Windows 访问 `http://<VM-IP>:8000/docs` 这类**绕过 nginx 的直连**，跨域会被拦。要么走 nginx，要么在 `.env` 里补：
> `CORS_ORIGINS=["http://<VM-IP>:5173","http://localhost:5173"]`（JSON 数组格式，pydantic-settings 按 complex 类型解析）。

---

## 6. 常用运维命令

```bash
docker compose logs -f backend              # 看后端日志
docker compose logs -f celery-worker        # 看异步任务（OCR）
docker compose restart backend              # 改了 .env 之后重启生效
docker compose restart celery-worker        # worker 不会热重载，改代码后必须重启
docker compose down                         # 停服务，保留数据卷
docker compose down -v                      # 连数据一起删
docker compose exec postgres psql -U finance -d finance   # 进数据库
./scripts/setup.sh --reset                  # 重置环境：删卷 + 重跑迁移 + seed
```

改了后端代码不用重建镜像——`./backend` 是挂载进去的，`uvicorn --reload` 会热重载。改了 **Celery worker 代码**要手动 `docker compose restart celery-worker`。改了依赖（`pyproject.toml`）才需要 `docker compose up -d --build backend celery-worker`。

---

## 7. 排查清单

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `permission denied while trying to connect to docker socket` | 当前用户不在 docker 组 | `sudo usermod -aG docker $USER` 后重新登录 |
| `bad interpreter: /bin/bash^M` | 脚本 CRLF | `dos2unix scripts/*.sh` |
| backend 一直 `starting`，连不上 PG | `DATABASE_URL` 里 host 写成 localhost；或两个密码不一致 | 改成 `postgres`，两边密码对齐 |
| `could not translate host name "postgres"` | 容器没在同一个 compose network | 确认都挂了 `finance-net`（默认如此），别单独 `docker run` |
| 上传发票后一直 pending_review | MinIO 不通 / celery worker 没起来 | `docker compose logs celery-worker`，确认 redis broker 地址是 `redis://redis:6379/1` |
| 页面能开但接口 404/502 | 走了 nginx 之外的端口 | 用 `http://<VM-IP>` 统一入口 |
| MinIO 里的图片下载链接打不开 | 预签名 URL 的 host 是容器名 `minio` | 属正常，仅容器内有效；从外部访问需把 `MINIO_HOST` 配成 VM IP 并暴露 9000 |
| 端口被占 (`address already in use`) | VM 里已装了 PG/Redis | 改 `.env` 里对应 `*_PORT`，或停掉宿主机上的同名服务 `sudo systemctl stop postgresql redis` |
| 构建卡在 `pip install` 超时 | 网络问题 | 换 pip 源：在 `backend/Dockerfile` 的 pip 行加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |

---

## 8. 生产化建议（现在不做，部署前记得）

- `APP_ENV=production`，后端去掉 `--reload`，改 gunicorn + uvicorn worker（`BACKEND_WORKERS`）
- 前端改成 `npm run build` + nginx 托管静态资源（现在跑的是 Vite dev server）
- `restart: unless-stopped` 已有；补 `.env` 的备份与密钥轮换
- Grafana / Prometheus 若不用，在 compose 里注掉省 2G 内存
