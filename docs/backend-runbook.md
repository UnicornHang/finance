# 后端服务运行手册

> 面向第一次接手这个项目的人。照着做就能把后端跑起来，不需要额外问任何人。
> 磁盘上的事实基准时间：**2026-09-25**

---

## 0. 三十秒看懂这套东西在干什么

后端是一个 **FastAPI 应用**，跑在 Docker 里，外面挂着三个基础设施依赖：

```
浏览器 ──► nginx:80 ──► frontend:5173 (vite dev server，代理转发)
                   └──► backend:8000  (FastAPI + uvicorn --reload)
                              ├──► postgres:5432   (业务数据 + pgvector)
                              ├──► redis:6379      (缓存 / Celery broker)
                              └──► minio:9000      (发票、合同、知识库文件)
                                     ▲
                        celery-worker 也在连这些
```

**一句话总结部署方式**：一个 `docker-compose.yml` 管全部，配置文件**只有根目录的那份 `.env`**，
启动命令就一行 `docker compose up -d backend celery-worker`（基础设施会被自动带起来）。

---

## 1. 先认识这几个文件

| 路径 | 作用 | 什么时候会碰它 |
|---|---|---|
| `docker-compose.yml` | **唯一的全栈编排文件**，定义了全部 9 个服务 | 加服务、改端口、改启动命令 |
| `.env` | **唯一生效的运行时配置**（根目录那份） | 填密钥、改密码 |
| `.env.example` | 配置模板 + 每项注释 | 生成 `.env` 时用一次 |
| `scripts/deploy-vm.sh` | 虚拟机内一键部署（幂等，可反复跑） | 换机器 / 重来时 |
| `scripts/setup.sh` | Windows / Mac 本机一键启动 | 用 Docker Desktop 时 |
| `scripts/smoke.sh` | 11 步端到端烟测，不用开浏览器 | **每次改完后端都要跑** |
| `backend/Dockerfile` | 后端镜像，`python:3.11-slim` | 加系统依赖时 |
| `docker-compose.infra.yml` | 只起基础设施的精简编排 | 想只跑 PG/Redis/MinIO 时用 |

### ⚠️ 最容易搞混的一点：项目里有两份 `.env`

```
finance/
├── .env              ← ✅ 容器内用它（host 全是服务名：postgres / redis / minio）
└── backend/.env      ← ❌ 这是「后端跑 Windows 本机」时的遗留配置，host 写的是具体 IP
```

**容器里的生效规则**：因为 compose 把 `./backend` 整个挂到了容器的 `/app`，`backend/.env` 会以
`/app/.env` 的身份混进容器，所以理论上两份文件都在容器里。代码里 `Settings` 是
**环境变量优先于 `.env` 文件**，而 compose 的 `env_file: .env` 会把根 `.env` 注入成真实环境变量，
所以才没出事——但这个依赖很脆弱。

> **建议：直接把 `backend/.env` 改名备份掉，全项目只留根目录 `.env`。**
> ```bash
> mv backend/.env backend/.env.win-local.bak
> ```

---

## 2. 端口速查

| 服务 | 容器名 | 容器内端口 | 映射宿主 | 说明 |
|---|---|---|---|---|
| FastAPI 后端 | `finance-backend` | 8000 | **8000** | Swagger 在 `/docs`，OpenAPI 在 `/api/v1/openapi.json` |
| Celery Worker | `finance-celery-worker` | — | 无 | 不对外暴露端口 |
| PostgreSQL(+pgvector) | `finance-postgres` | 5432 | 5432 | 镜像 `pgvector/pgvector:pg16` |
| Redis | `finance-redis` | 6379 | 6379 | `redis:7-alpine` |
| MinIO API | `finance-minio` | 9000 | 9000 | S3 兼容对象存储 |
| MinIO 控制台 | `finance-minio` | 9001 | **9001** | 浏览器登录用 |
| 前端 dev server | `finance-frontend` | 5173 | 5173 | 仅 `--all` 模式起 |
| Nginx | `finance-nginx` | 80 / 443 | **80 / 443** | 推荐入口，前后端同源 |
| Prometheus | `finance-prometheus` | 9090 | 9090 | 可选 |
| Grafana | `finance-grafana` | 3000 | 3000 | 可选 |

---

## 3. 环境前提

我们当前跑在 Ubuntu 虚拟机上，这是**已验证可行的配置**：

| 项 | 实测值 | 最低要求 |
|---|---|---|
| OS | Ubuntu 22.04+，内核 6.8 | Ubuntu 20.04+ |
| CPU | 4 核 | 2 核 |
| 内存 | 1.9G（**跑完后端核心只剩 ~900M，偏紧**） | **建议 4G** |
| 磁盘 | 79G，可用 65G | **建议 ≥20G**（单个镜像 2.1G，首次构建约 5G） |
| Docker | 29.8.1 | v20+ |
| Docker Compose | 5.5.1（plugin 形态，命令是 `docker compose` 带空格） | v2 |

> **强烈建议把虚拟机内存调到 4G。** 现在 5 个容器实测占用约 640M，一旦加前端容器就会吃紧。

### VMware 网络建议用「桥接」

桥接模式下虚拟机会拿到一个和 Windows 同网段的独立 IP，Windows 直接开 `http://<VM-IP>` 就行，
走 nginx 同源、没有跨域问题。NAT 模式则需要手动转发 80 / 5173 / 8000 / 9001 四个端口。

---

## 4. 第一次上手（照抄执行）

### 4.1 拿代码

虚拟机里**必须 git clone**，别用 scp 从 Windows 拷（`.gitignore` 已排除 `node_modules/`、`.venv/`、`.env`）：

```bash
git clone -b main git@github.com:UnicornHang/finance.git ~/finance
```

> 如果之前是 scp 拷过去的目录（**当前这台 VM 就是这样**），它不是 git 仓库，改代码只能 scp 覆盖，
> 长期会版本漂移。补救办法：
> ```bash
> cd ~/finance
> git init && git remote add origin git@github.com:UnicornHang/finance.git
> git fetch origin && git reset --hard origin/main
> ```

### 4.2 生成 `.env`

```bash
cd ~/finance
cp .env.example .env
```

**必改的几项**（不改服务也能起，但这是安全的底线）：

```bash
# 生成两个随机密钥（别手搓）
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -hex 32)|" .env
sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$(openssl rand -base64 32)|" .env

# 数据库密码 —— 改了必须同步改 DATABASE_URL 里那串，两处必须一致
POSTGRES_PASSWORD=<你的密码>
DATABASE_URL=postgresql+asyncpg://finance:<同一个密码>@postgres:5432/finance

# 其余默认密码也建议改
MINIO_ROOT_PASSWORD=...
GRAFANA_ADMIN_PASSWORD=...
```

**AI 能力相关**（填了对话才可用，见 §6）：`LLM_*_API_KEY`、`EMBEDDING_API_KEY`、`TENCENT_OCR_SECRET_*`

### 4.3 启动

用现成的部署脚本最省事（幂等，反复跑不会出事）：

```bash
bash scripts/deploy-vm.sh          # 后端核心：PG + Redis + MinIO + backend + celery
bash scripts/deploy-vm.sh --all    # 全套：再加 frontend + nginx + prometheus + grafana
```

等价的手动命令：

```bash
docker compose up -d backend celery-worker
```

> compose 里 `backend` 写了 `depends_on: postgres/redis/minio (condition: service_healthy)`，
> 所以**不需要单独先起基础设施**，会自动带起来并按健康检查结果排序。

**首次构建要 10–20 分钟**（langchain / litellm 那批依赖很重）。如果之前构建过镜像
（`finance-backend`、`finance-celery-worker` 各 2.1G），几十秒就起来了。

### 4.4 启动时自动做了两件事

后端容器的启动命令是这样的：

```yaml
command: >
  sh -c "alembic upgrade head &&
         python scripts/seed.py || echo '⚠️  seed skipped or failed' &&
         uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
```

1. **数据库迁移**：`alembic upgrade head`，跑 `backend/alembic/versions/` 下的迁移脚本（当前 001、002）
2. **种子数据**：`scripts/seed.py` 建 3 个用户、4 条 LLM 配置、2 条知识库记录
   —— **这个脚本是幂等的**（检测到 `admin` 已存在就 `用户已存在，跳过`），所以重启容器不会重复灌数据

最后才是 `uvicorn --reload`。MinIO 的三个桶（`invoices` / `contracts` / `knowledge-base`）由应用代码自动创建。

### 4.5 验证

```bash
# 1) 健康检查
curl -s http://localhost:8000/health
# 期望：{"status":"ok","env":"development","version":"1.0.0"}

# 2) 端到端烟测（11 步，不用开浏览器）
BASE_URL=http://localhost:8000 bash scripts/smoke.sh
# 期望结尾：14 通过 / 0 失败 / 0 警告
```

如果 VM 网络是桥接，在 Windows 上也能直接验证：

```bash
curl -s http://192.168.8.128:8000/health
```

### 4.6 默认账号

| 账号 | 密码 | 角色 |
|---|---|---|
| `admin` | `Admin@123` | 管理员 |
| `finance01` | `Finance@123` | 财务 |
| `employee01` | `Emp@123` | 员工 |

MinIO 控制台：默认 `minio_admin` / `minio_pass_change_me`（如果没改的话）。

---

## 5. 日常运维

```bash
cd ~/finance
DC="docker compose"

$DC ps                              # 看容器状态（healthy 才是真就绪）
$DC logs -f backend                 # 跟日志，-f 退出加 Ctrl+C
$DC logs --tail=100 backend         # 只看最后 100 行
$DC restart backend                 # 重启
$DC down                            # 停止并移除容器（volumes 保留，数据不丢）
$DC down -v                         # ⚠️ 连同 volumes 一起删，数据全清
$DC up -d --build backend           # 改了依赖后重新构建
$DC exec backend alembic upgrade head   # 单独跑迁移
$DC exec postgres psql -U finance -d finance   # 进数据库
```

### ⚠️ 改代码后的生效规则

| 改了什么 | 要不要重启 | 命令 |
|---|---|---|
| `backend/**/*.py` | **不用** | compose 挂了 `./backend:/app` + `--reload`，保存即热重载 |
| **`app/tasks/`、`app/workers/`（Celery 侧）** | **必须手动重启** | `docker compose restart celery-worker` |
| `pyproject.toml`（依赖） | 必须重建 | `docker compose up -d --build backend celery-worker` |
| `.env` | 必须重启（环境变量在容器启动时注入） | `docker compose restart backend celery-worker` |

> 别踩：**uvicorn 的 `--reload` 只管 API 进程，不管 Celery worker。** 改了异步任务代码不重启 worker，
> 跑的还是旧代码，而且不会有任何报错。

---

## 6. AI 能力配置（不填就是残废）

`app/config.py` 把 LLM 拆成了**四个场景槽位**，每个槽位有自己的 model / key / base_url，
统一走 LiteLLM，**只要接口是 OpenAI 兼容的就能直接用**（OpenAI、DeepSeek、通义、智谱、本地 vLLM 等）。

| 环境变量 | 用途 | 不填会怎样 |
|---|---|---|
| `LLM_CHITCHAT_*` | 日常对话 | 对话返回 `[LLM 调用失败: ... Missing credentials]` |
| `LLM_POLICY_*` | 财务制度问答 / RAG | 知识库问答不可用 |
| `LLM_OCR_*` | **发票 Vision 识别（当前主路径）** | 走 Mock 降级，生成假的「模拟发票 XXXX」 |
| `LLM_CONTRACT_*` | 合同审查 | 合同审查不可用 |
| `EMBEDDING_*` | RAG 向量化 | 知识库检索不可用 |
| `TENCENT_OCR_SECRET_ID/KEY` | 腾讯云 OCR（老路径） | 代码有 Mock 降级，服务不会崩 |

以 DeepSeek 为例，四个槽位照着填：

```bash
LLM_CHITCHAT_MODEL=deepseek-chat
LLM_CHITCHAT_API_KEY=sk-xxxx
LLM_CHITCHAT_BASE_URL=https://api.deepseek.com/v1
# POLICY / OCR / CONTRACT 三个槽位同理
EMBEDDING_API_KEY=sk-xxxx
EMBEDDING_BASE_URL=https://api.deepseek.com/v1
```

改完记得 `docker compose restart backend celery-worker` —— **改 `.env` 不重启是不生效的。**

---

## 7. 前端怎么连后端（这里最容易踩坑）

### 三种部署形态对照

| 形态 | 浏览器入口 | `VITE_API_BASE_URL` | `VITE_API_PROXY_TARGET` |
|---|---|---|---|
| **A. 全套都在 VM 容器里** | `http://<VM-IP>` (nginx 80) | 留空 | compose 里已写死 `http://backend:8000` ✅ 不用管 |
| **B. 后端在 VM，前端跑 Windows 本机 `npm run dev`** | `http://localhost:5173` | 留空 | **必须设 `http://<VM-IP>:8000`** ⚠️ |
| **C. 前后端全跑 Windows 本机** | `http://localhost:5173` | 留空 | 不设，自动 fallback 到 `http://localhost:8001` |

### 形态 B 的正确做法（我们当前就是这种）

新建 `frontend/.env.local`（**这个文件被 `.gitignore` 覆盖，不会提交，适合放机器相关的 IP**）：

```bash
VITE_API_PROXY_TARGET=http://192.168.8.128:8000
```

### 为什么必须这么做 —— 两个连环坑

**坑 1：`vite.config.ts` 里的 `process.env` 读不到 `.env` 文件！**

Vite 是在**配置文件解析之后**才加载 env 文件的，所以：

```ts
target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8001'   // ❌ .env.local 被静默忽略
```

必须显式调用 `loadEnv`（当前仓库里的 `vite.config.ts` 已经修好了）：

```ts
import { defineConfig, loadEnv } from 'vite'
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname)
  const apiTarget = process.env.VITE_API_PROXY_TARGET || env.VITE_API_PROXY_TARGET || 'http://localhost:8001'
  ...
})
```

**坑 2：代理失败在浏览器里表现为 500，不是 502/504**

转发到空端口时，vite dev server 给浏览器返回的是 **500**，响应体 0.2kB、耗时个位数毫秒。
看着就像后端崩了，其实后端一点事没有。

> 这个症状确实在我们环境里出现过：**`/sessions/` 报 500**，翻遍后端日志只有无关的 LLM 报错，
> 最后发现是代理指向了没人监听的 `localhost:8001`。

### CORS 提醒

默认 `CORS_ORIGINS` 只放行 `localhost:5173`。**绕过 nginx 直接访问 `:8000` 会被拦**，需要补：

```bash
CORS_ORIGINS=["http://localhost:5173","http://192.168.8.128:5173"]
```

注意必须是 **JSON 数组格式**。最省事的办法就是走 nginx 80 同源，别折腾跨域。

---

## 8. 排障手册

### 决策树：接口 5xx，先分清是谁的锅

```bash
# ① 直连后端（带 token 才是真实情况）
curl -s -w "\nHTTP %{http_code}\n" http://192.168.8.128:8000/api/v1/sessions/ \
  -H "Authorization: Bearer <token>"

# ② 再经前端代理
curl -s -w "\nHTTP %{http_code}\n" http://localhost:5173/api/v1/sessions/
```

- ① 正常、② 是 500 → **问题在 vite 代理配置**，别去翻后端日志，看 §7
- ① 也挂 → 继续往下查

### 常见症状对照表

| 症状 | 原因 | 怎么查 / 怎么修 |
|---|---|---|
| 容器起来就退出 | 多半是 `.env` 缺变量或格式错 | `docker compose logs backend \| tail -50` |
| `/health` 一直不通 | 迁移没跑完，或 PG 还没 healthy | `docker compose logs backend`；`docker compose ps` 看 PG 是不是 healthy |
| 后端连不上数据库 | **`.env` 里 host 填了 localhost 或具体 IP** | 容器内必须用服务名，见 §9 第 1 条 |
| 改了 Python 代码没生效 | 该文件在 Celery 侧 | `docker compose restart celery-worker` |
| 改了 `.env` 没生效 | 环境变量在容器启动时注入 | `docker compose restart backend celery-worker` |
| 前端接口全 500、响应体很小 | vite 代理 target 指向空端口 | §7 |
| 快，2 位数毫秒就 500 | 同上，代理层问题（真实后端不会这么快失败） | §7 |
| `/chat/stream` 200 但内容是 `[LLM 调用失败: Missing credentials]` | LLM key 没配 | §6，四个槽位都要填 |
| 脚本 `/bin/bash^M: bad interpreter` | Windows 拷过去带了 CRLF | `sed -i 's/\r$//' scripts/*.sh` |
| 构建时报找不到 README | `pyproject.toml` 里写了 `readme = "README.md"` | Dockerfile 里已 `COPY pyproject.toml README.md ./`，别删 |
| 第二个接口开始报 unique constraint | 烟测/测试脚本用了硬编码编号 | 加时间戳后缀；已修在 `scripts/smoke.sh` |
| 本机 Windows 侧的 `backend/.env` 改了没反应 | 容器用的是根目录 `.env` | §1 |

### 查日志的正确姿势

```bash
# 后端
docker compose logs -f backend
# 只看异常堆栈
docker compose logs --tail=200 backend 2>&1 | grep -E "Traceback|Error|File \"/app" 
# Celery
docker compose logs -f celery-worker
# 看 Redis 队列里有没有堆积（LLEN 长期 > 0 说明 worker 没消费）
docker compose exec redis redis-cli -n 1 LLEN celery
```

> 关于 Celery：`redis:6379/1` 是 broker，`/2` 存结果。
> **当前代码里没有任何 `.delay()` 调用** —— commit `67fa1e7` 起发票识别改成 Vision 同步主路径
> （`chat_service` 直接调 `invoice_vision_service.recognize()`），
> `process_invoice_ocr`、`contract_review_task` 这两个任务还注册着但**没人调用**。
> 所以 worker 日志里看不到任务执行是**正常的，不是故障。**

---

## 9. 五个必须记住的约定

1. **容器内所有 host 必须是 compose 服务名**（`postgres` / `redis` / `minio`），
   不能写 `localhost`（那是容器自己），也不能写 VM IP（多层 NAT 且重建后 IP 会变）。

   ```bash
   POSTGRES_HOST=postgres
   REDIS_HOST=redis
   MINIO_HOST=minio
   CELERY_BROKER_URL=redis://redis:6379/1
   DATABASE_URL=postgresql+asyncpg://finance:<pwd>@postgres:5432/finance
   ```

2. **`scripts/*.sh` 必须是 LF 换行**。从 Windows 拷到 Linux 会变成 CRLF，
   报 `bad interpreter: /bin/bash^M`。落库前先 `sed -i 's/\r$//'`。

3. **`.gitignore` 已经排除了 `node_modules/`、`.venv/`、`.env`**。跨平台拷贝代码时这三个绝对不能带过去 ——
   Windows 的 `node_modules` 里有原生二进制，`.venv` 里的 python 路径也不通用。

4. **登录接口是 `application/x-www-form-urlencoded`，不是 JSON。** 写测试脚本时别踩。

5. **改完后端一定跑 `scripts/smoke.sh`**（当前预期 `14 通过 / 0 失败 / 0 警告`）。
   它能揪出单看日志发现不了的问题。

---

## 10. 当前环境快照（2026-09-25 实测）

| 项 | 值 |
|---|---|
| VM IP / 主机名 | `192.168.8.128` / `dpcker-vm` |
| SSH | `ssh ubuntu@192.168.8.128`（已配密钥免密） |
| 代码位置 | `~/finance`（**当前还不是 git 仓库**，靠 scp 同步，有漂移风险） |
| 运行中的容器 | `finance-backend`(healthy)、`finance-celery-worker`、`finance-postgres`(healthy)、`finance-redis`(healthy)、`finance-minio`(healthy) |
| 内存占用 | backend 317M、celery 159M、minio 112M、postgres 45M、redis 6M，合计约 640M |
| 访问地址 | `http://192.168.8.128:8000/health`、`http://192.168.8.128:9001`（MinIO） |
| 已配密钥 | 无。LLM / Embedding / OCR 的 key **全是空的**，识别走 Mock 降级 |
| 前端 | 跑在 Windows 本机 `localhost:5173`，通过 `frontend/.env.local` 指向 VM |

**已知待办**：
- [ ] VM 内存从 1.9G 提到 4G
- [ ] `~/finance` 改成 git 仓库，用 pull 而不是 scp 同步
- [ ] 备份掉 `backend/.env`，消除双 `.env` 隐患
- [ ] 补齐 LLM key（§6）
