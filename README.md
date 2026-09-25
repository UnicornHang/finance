# finance

> 以对话为入口的企业财务 AI Agent 平台，完成发票/合同的智能识别、结构化归档、合规审查与制度问答。

## 核心能力

- 🧾 **发票智能识别**：上传即识别，AI 结构化提取，人工确认后归档
- 📜 **合同合规审查**：自动解析、RAG 规则匹配、风险等级标注
- 💬 **制度问答**：RAG 检索 + LLM 生成，附来源引用
- 🔒 **多租户隔离**：行级权限 + tenant_id 强制过滤，私有化部署 + SaaS 演进
- 🛡️ **会话隔离**：完整历史 + 摘要 + 结构化记忆 + RAG 四层上下文策略

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + shadcn/ui + TailwindCSS + Vite + Zustand |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 + LangChain + Celery |
| 数据 | PostgreSQL 16 + pgvector + Redis + MinIO |
| AI | LangChain + LiteLLM（GPT-4o / Claude / 通义 / 本地模型可配置） |
| 部署 | Docker + Nginx + Prometheus + Grafana |

## 仓库结构

```
finance/
├── backend/                # FastAPI 后端
├── frontend/               # React 前端
├── nginx/                  # 反向代理配置
├── db/                     # 数据库初始化脚本
├── scripts/                # 运维脚本
├── docs/                   # 产品 + 技术文档
└── docker-compose.yml      # 一键启动
```

## 快速开始

### 前置条件

- Docker 24+ / Docker Compose v2
- 8GB+ 可用内存
- 100GB+ 磁盘空间

### 启动开发环境

```bash
# 一键启动（推荐）：自动复制 .env → 启动服务 → 等待 healthy → seed 数据
./scripts/setup.sh              # Git Bash / WSL
# 或 Windows PowerShell：
# .\scripts\setup.ps1
```

> 重置环境（删除 volumes 重新来）：`./scripts/setup.sh --reset`

启动后访问：

| 地址 | 用途 |
|---|---|
| http://localhost | **推荐入口**（nginx 反代，前端 + API 同源） |
| http://localhost:5173 | 前端直连（仅调试时用，容器内 vite proxy 已自动指向 backend 服务） |
| http://localhost/docs | Swagger API 文档 |
| http://localhost:9001 | MinIO 控制台 |

### 端到端烟测

```bash
./scripts/smoke.sh
# 11 步覆盖：health → 登录 → /me → /sessions → SSE 流式 → 消息历史 → /llm/providers + /llm/configs → /invoices/archive → multipart 上传 → confirm + 列表查询
```

### 手动分步启动（如需自定义）

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 修改关键配置（JWT_SECRET / 第三方 API Key）
vim .env

# 3. 启动所有服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f backend
```

### 默认账号

| 账号 | 密码 | 角色 |
|---|---|---|
| admin | Admin@123 | 管理员 |
| finance01 | Finance@123 | 财务 |
| employee01 | Emp@123 | 员工 |

> 首次登录强制修改密码。

### 本地开发（无 Docker）

```bash
# 后端
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

## 文档导航

- [PRD 产品需求文档](docs/prd.md)
- [TD 技术选型与架构设计](docs/TD.md)
- [后端运行手册](docs/backend-runbook.md)
- [Ubuntu 虚拟机 Docker 配置](docs/ubuntu-docker-setup.md)

## 路线图

- **Phase 1（4-6 周）**：登录 + Chat + 发票 OCR 归档
- **Phase 2（4 周）**：合同审查 + RAG 知识库
- **Phase 3（3 周）**：制度问答 + 后台看板 + 权限细化

### Phase A 完成情况（2026-09）

发票 OCR 归档全链路已实现：

- ✅ 通用上传接口 `POST /api/v1/files/upload`（multipart）落 MinIO（与具体业务解耦）
- ✅ **选完即传**：Chat 输入框选中文件立刻调 `/files/upload`（显示"上传中→已上传"状态），不阻塞用户继续输入
- ✅ 用户点击发送时只携带 `file_url` + `file_hash` 进 `POST /api/v1/chat/stream`（JSON 体）；chat_service 根据 LLM 语义决定调用 OCR / 文档解析 / 直接问答
- ✅ 腾讯云 OCR Provider + Mock 降级（无密钥时不崩）——**2026-09-25 起主路径已改为大模型识别，见下方「当前进度」**
- ✅ 右栏持久轮询 `/invoices/preview/by-hash/{hash}` 实时刷新识别进度——主路径改为同步推送侧栏，轮询接口仍保留
- ✅ 用户确认 → `status: pending_review → active` 归档
- ✅ 唯一约束 `(tenant_id, invoice_code, invoice_number)` 硬去重（409）
- ✅ 行级权限：员工仅看自己的发票；财务/管理员看全部
- ✅ 审计日志：编辑/确认/删除均落 audit_logs
- ✅ MinIO 预签名下载 URL（默认 1h 过期）
- ✅ 后台档案页：分页 + 类型/状态筛选 + CSV 导出 + 详情对话框
- ✅ LLM 场景配置新增 `system_prompt` 字段持久化

详细验收清单见 [docs/PRD.md §Phase A 验收](docs/PRD.md)。

### Phase A+ UI/UX 增量（2026-09-23）

Phase A 验收之后、Phase B 启动之前的打磨批次，仅改管理后台与会话界面，主链路 / 数据模型未动：

- ✅ shadcn/ui 全面替换手搓下拉 / 原生 confirm/prompt/alert / 原生 select，新增 [AGENT.md](AGENT.md) 工程规约
- ✅ LLM 设置：API Key 显式录入 + `system_prompt` 多行编辑（持久化至 `llm_configs.system_prompt`）
- ✅ 编辑态「测试连接」按钮 + 错误分级提示（4xx 高亮字段 / 5xx 重试入口 / 网络断开重试）
- ✅ 流式渲染抽出 `StreamRenderer`，错误事件统一带复制按钮
- ✅ 会话侧栏重构为 DeepSeek 风格：今天 / 昨天 / 本周 / 本月 / 更早 时间桶 + 用户底部信息条
- ✅ **通用上传 + Chat 三栏右栏持久展示**（2026-09-24）：
  - 后端 `POST /api/v1/files/upload` 通用 multipart 上传（只落 MinIO，不触发业务逻辑）
  - 后端 `POST /api/v1/chat/stream` 改为 JSON 体：客户端先 `/files/upload` 拿 `file_url`/`file_hash`，再把它们随消息一起进 SSE 流，chat_service 由 LLM 决定是 OCR / 文档解析 / 直接问答
  - **输入框选文件即触发上传**（不阻塞文本输入，显示"上传中 / 已上传 / 失败"状态；失败可点 × 重选；切换文件 abort 进行中的上传）
  - Chat 页改为两栏 / 三栏自适应：有发票 / 合同结构化数据时右栏持久出现，否则保持两栏
  - InvoicePanel / ContractPanel 容器从 shadcn `Sheet` 抽屉改为持久 `<aside>`，所有表单 / 轮询 / 确认逻辑 1:1 保留
  - 输入框选文件 → "上传 → 发送"两步走（不再有独立的 sidebar 上传按钮）

详细改动清单见 [docs/PRD.md §Phase A+ 增量](docs/PRD.md)。

### 当前进度（2026-09-25）

Phase A 发票归档仍可用。识别与对话主路径已从「腾讯 OCR + Celery 轮询」切到「大模型同步识别 + 按文件分流」。合同审查、知识库 RAG、制度问答仍未进入正式交付。

**已落地**

- ✅ 发票识别主路径：上传后由多模态模型同步抽取字段，结果直接入库（`pending_review`）并经 SSE 推到右栏；回复里带上结构化字段。Celery `process_invoice_ocr` 仍在注册，主链路不再调用。
- ✅ 上传分流：模型先判断附件是发票、合同还是普通文件，再进入识别、合同审查或日常对话。合同目前是场景模型的文本审查，没有归档和 RAG。
- ✅ 识别不再回落 OCR 引擎。未配置可用密钥时直接提示去系统设置填写「日常对话」或「单据识别」的 API Key。图片走多模态；PDF/Word 先抽文本再交给同一模型。
- ✅ 聊天气泡回显附件：`POST /api/v1/files/presign` 按租户和白名单桶签发临时链接；消息持久化 `attachments`；支持图片大图、文件卡，以及只发附件不写文字。
- ✅ 场景级 `system_prompt`：管理后台配置后替换该场景默认人设；读取失败回落默认提示词。LLM 设置对话框加宽，提示词输入区加大。
- ✅ 部署：后端跑在 Ubuntu 虚拟机 Docker（`192.168.8.128:8000`）。`scripts/deploy-vm.sh` 幂等拉起 backend + celery（自动带起 postgres / redis / minio）。本机 Vite 通过 `VITE_API_PROXY_TARGET` 代理到该地址。
- ✅ 修复：发票审计日志参数名、422 响应里 bytes 无法 JSON 序列化、`vite.config.ts` 未加载 `.env.local` 导致会话接口 500、`scripts/smoke.sh` 与现网 JSON 上传流程对齐。烟测 **14 通过 / 0 失败 / 0 警告**。

**尚未完成**

- 对话和识别依赖已配置的 LLM API Key。虚拟机根目录 `.env` 里相关密钥仍为空时，接口能通，内容会报缺凭证。
- Phase 2：合同正式归档、合规规则 RAG、会话摘要与结构化记忆。
- Phase 3：制度问答、看板、权限细化、RAG 历史检索。

手册见 [docs/backend-runbook.md](docs/backend-runbook.md)。验收对照见 [docs/PRD.md §当前进度](docs/PRD.md)。

