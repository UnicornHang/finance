# Agent / RAG / 运维改进改动方案

| 项 | 内容 |
|---|---|
| 状态 | 迭代 1（P0）实施中：P0-1～P0-9 代码已合入本分支，待联调验收 |
| 前置 | B1 文本 LangGraph 已接入；B2 记忆 / 追问 / 观测骨架已落地 |
| 关联 | [B1](agent-langchain-langgraph.md)、[B2](agent-b2.md)、[对话检索架构调整](对话检索架构调整.md)、[RAG-KB-Design](RAG-KB-Design.md)、`docs/TD.md` §5 |
| 原则 | 硬门禁写在代码；归档必须人确认；先修正确性与合规，再优化延迟与扩展 |

---

## 1. 背景与结论

当前主链路（意图分类 → 白名单工具 → 混合 RAG / 权威检索 → SSE 流式 → 侧栏 HITL 归档）已可支撑 MVP。审计后确认：

**做得好的**

- 意图硬白名单 + 工具节点二次校验（`policy.py` / `graph.py`）
- 归档不开放给模型 Tool；侧栏 REST + `confirm_pending`
- 企业知识库：切分 → Milvus/PG 混合 → RRF → 可选 Rerank → 分数门槛
- 会话记忆：窗口 / 摘要 / 实体 / 条件历史召回

**最大实质风险**

1. 制度意图下强制补调优先外网（串源）
2. 文档与代码拓扑 / 闲聊工具策略漂移
3. 限流、JWT `tenant_id`、`/metrics` 等生产安全未闭环
4. 制度侧引用不可点回；Rerank 归一化与 0.35 门槛冲突

本方案按 **P0 → P1 → P2** 分三迭代落地；**不做**多 Agent Supervisor、Graph Checkpointer 等人确认、把发票/合同做成可写 Tool。

---

## 2. 目标与非目标

### 2.1 目标

| 优先级 | 目标 | 可验收结果 |
|---|---|---|
| **P0** | 门禁正确、文档对齐、生产底线安全、制度可溯源 | 制度问不会被强制外网污染；限流生效；制度回答可点看来源 |
| **P1** | 降延迟、可观测成链路、评测可回归、单据管道收敛 | 工具后流式或真回环；一轮一个 trace；黄金问进 CI；Celery 双轨消除 |
| **P2** | 工具可扩展、召回增强、质量闭环 | 本地/MCP 统一注册表；稀疏召回升级；反馈回写 |

### 2.2 非目标（明确不做）

| 不做 | 原因 |
|---|---|
| Supervisor 多 Agent | 过重；单图 + 硬路由已够 |
| LangGraph Checkpointer 跨请求等人确认 | 确认已是侧栏 HTTP；避免双写状态 |
| `archive_*` / `ocr_*` 作为模型可调 Tool | 模型会在未确认时落库 |
| 历史消息全量向量 RAG（PRD 第四层） | 与会话摘要重叠；仍放后续 B3 |
| 一次性大改前端视觉 | 本方案偏编排与后端正确性 |

---

## 3. 与现行设计的冲突点（必须先拍板）

以下条目代码与文档已不一致，**迭代 1 必须二选一对齐**，禁止继续双口径。

| 冲突 | 文档说法 | 代码现状 | 本方案裁定 |
|---|---|---|---|
| 图拓扑 | B1：`tools → agent` 最多 2 轮 | `tools → finalize` 单向 | **P1 再决定**是否真回环；P0 先改文档为「单次 tools→finalize」 |
| 漏调补救 | B1：软提醒，不强制 | `_ensure_retrieval_call` → `force_tool` | **保留强制补调**，但按意图分化默认工具（见 §4.1） |
| 闲聊工具 | B2：闲聊默认无工具 | `CHITCHAT` 开放双检索 | **保留可调**（与[对话检索架构调整](对话检索架构调整.md)一致），但**不强制**；补「闲聊误搜」回归用例 |
| 强制补调默认 | 未写清 | 优先 `search_official_data` | **按意图**：制度优先知识库，公开优先外网 |
| SSE `sources` | B1 未列 | 编排器已发，前端已接 | **文档补齐** `sources` 事件 |

---

## 4. 改动清单（按优先级）

### 4.1 P0 — 正确性 / 合规 / 安全

#### P0-1 按意图分化强制补调默认工具

**问题**：`graph.py` 中 `_fallback_retrieval_call` 在白名单同时含两工具时优先外网；`policy_query` 漏调也会强制 `search_official_data`，污染制度上下文。单测已固化该行为。

**改动**

```text
_fallback_retrieval_call(intent, allowed, question):
  if intent == POLICY_QUERY and query_policy in allowed → 强制 query_policy
  if intent == PUBLIC_TAX and search_official in allowed → 强制 search_official
  # 仅当目标工具不在白名单时，才退到另一个
```

语义补调 JSON（`_semantic_retrieval_call`）仍优先于 fallback；模型已合法选工具时不改。

**涉及文件**

- `backend/app/agent/graph.py`（`_fallback_retrieval_call` / `_ensure_retrieval_call`）
- `backend/tests/test_agent_graph.py`（改写「差旅补贴强制外网」用例为「强制 query_policy」）

**验收**：制度类问句漏调时只补 `query_policy`；公开财税漏调时只补 `search_official_data`。

**落地**：已改 `graph.py` `_fallback_retrieval_call(intent, …)`；`test_agent_graph.py` 已改写差旅用例并新增闲聊不强制补调。

---

#### P0-2 收敛文档与代码

**改动**

- 更新 `docs/agent-langchain-langgraph.md`：拓扑改为 `agent → tools → finalize`；写明强制补调与意图默认；SSE 增加 `sources`
- 更新 `docs/agent-b2.md`：闲聊工具策略改为「可调不强制」，与 `对话检索架构调整.md` 一致
- `docs/provide.md`：删除或改写「调用 MCP」人设，与 `chat_service`「不要声称调用了 MCP」对齐

**验收**：三份 Agent 文档与 `policy.py` / `graph.py` 行为一致，无互相矛盾条款。

**落地**：已更新 `agent-langchain-langgraph.md`、`agent-b2.md`、`provide.md`。

---

#### P0-3 闲聊工具策略正式化 + 回归用例

**裁定**：闲聊**允许**两工具、**不**走 `needs_retrieval` 强制补调（现状已如此）。

**补强**

- 单测：问候类不触发 `force_tool`
- 单测：闲聊误标后若模型乱调外网，回答约束仍禁止「编造联网」口吻（可对 prompt / observe 断言）
- 管理端或日志：记录 `intent=chitchat` 且发生 tool_call 的比例，便于后续是否收紧

**涉及文件**：`backend/tests/test_agent_policy.py`、`test_agent_graph.py`

**落地**：`test_graph_chitchat_does_not_force_tool` 已加。

---

#### P0-4 鉴权：JWT `tenant_id` 与 DB 交叉校验

**改动**：`get_current_user` 在用 `sub` 加载用户后，校验 `payload.tenant_id == user.tenant_id`（claim 缺失或不等则 401）。

**涉及文件**

- `backend/app/api/deps.py`（或实际 deps 模块）
- `backend/app/core/security.py`（签发侧保证写入 `tenant_id`）
- 相关 auth 单测

**验收**：伪造 / 篡改 tenant claim 无法访问他租户数据。

**落地**：`deps.get_current_user` 已交叉校验；`test_auth_flow.py` 覆盖 mismatch。

---

#### P0-5 限流落地

**问题**：`config.rate_limit_per_user / tenant / ip` 已有，代码无中间件引用。

**改动**

- 引入 Redis 滑动窗口或 slowapi；优先挂在：
  - `POST /api/v1/chat/stream`
  - 工具连通性测试、LLM 连通性测试
  - 文件上传
- 超限返回 429 + 明确文案；按 user 为主、IP 为辅

**涉及文件**：`backend/app/main.py`、新建 `backend/app/core/rate_limit.py`、`backend/app/config.py`

**验收**：压测单用户超 `rate_limit_per_user` 返回 429；配置项可调。

**落地**：新增 `core/rate_limit.py`；挂到 chat/stream、files/upload、tools/llm 试连；`test_rate_limit.py`。

---

#### P0-6 保护 `/metrics`

**改动**：内网 CIDR 白名单，或 Basic Auth / 独立监听地址；`deploy-prod.sh` / nginx 与 Prometheus scrape 配置同步。

**涉及文件**：`backend/app/main.py`、`nginx/*`、`scripts/deploy-prod.sh`、`docs/deploy-production.md`

**落地**：`MetricsProtectMiddleware` + `METRICS_TOKEN` / 本机回环；`.env.example` 已补配置。Prometheus 若异机 scrape，需配置 Bearer token。

---

#### P0-7 制度检索可追溯（policy sources）

**问题**：公开检索有 `[n]` + SSE `sources`；制度侧仅标题+正文，无 `doc_id` / `chunk_id` / 可点击来源。

**改动**

1. `query_policy` 返回带稳定编号的片段：`【制度1】` + `doc_id` / `chunk_id` / `section_path` / 标题
2. Orchestrator 在制度命中后发 SSE `{ type: "sources", items: [...] }`（字段与公开检索对齐，可加 `kind: "policy"`）
3. 前端 `SearchSourcesBar` 展示制度来源（可区分「企业制度」与「权威网站」）

**涉及文件**

- `backend/app/agent/tools/catalog.py`
- `backend/app/agent/orchestrator.py`
- `frontend/src/components/chat/SearchSourcesBar.tsx`
- `frontend/src/hooks/useSSE.ts`（若类型需扩展）

**验收**：制度问答气泡下可看到来源列表；点击可定位到知识库文档（或至少展示标题+路径）。

**落地**：`catalog.policy_sources_from_hits` + orchestrator 合并 SSE；前端 `SearchSourcesBar` / `readSearchSources` 支持 `source_kind=policy`。

---

#### P0-8 Rerank 分数与 0.35 门槛解耦

**问题**：`normalize_rerank_scores` 做 batch min-max 后，用绝对门槛 `POLICY_RAG_MIN_SCORE=0.35` 会把一批弱相关抬成「高分」。

**改动**

- 门槛比较使用 **原生 relevance**（或单独校准映射），禁止用 min-max 后的分直接对 0.35
- 无 rerank 时：明确用向量分 / RRF 导出分的哪一种，并写进 `policy.py` 注释与配置
- 单测覆盖「一批全弱相关 → 全部低于门槛」

**涉及文件**：`backend/app/services/rag_hybrid.py`、`rerank_service.py`（若有）、`agent/policy.py`、`tests/test_rag_hybrid.py`

**落地**：`normalize_rerank_scores` 对 logits 改用 sigmoid，去掉 batch min-max；弱批次单测已覆盖。

---

#### P0-9 幽灵向量治理（最小切片）

**改动**

- `_cleanup_old_vectors` 失败写入可重试队列或审计日志表（doc_id + 旧 vector ids）
- 提供管理端或脚本：按 `doc_id` 强制 purge Milvus 中不在 PG active chunks 的向量
- 可选：启动/定时对账任务（可放 P1 若工作量大）

**涉及文件**：`backend/app/services/kb_indexing.py`、`milvus_service.py`

**落地**：清理失败入 `_STALE_VECTOR_QUEUE`；提供 `retry_stale_vector_cleanups` / `purge_doc_vectors`；下次索引前自动冲刷队列。

---

### 4.2 P1 — 延迟 / 可观测 / 管道成熟度

#### P1-1 工具环与流式合并

**现状**：图内 `ainvoke`（含可能的语义补调 LLM）→ 出图后再 `stream_llm_and_persist`，约 3～4 次 RTT；agent 步正文被丢弃。

**方案（二选一，实施前 ADR 一行）**

| 方案 | 做法 | 适用 |
|---|---|---|
| A. 减一跳 | 工具结果后直接流式生成，取消「整图结束再开一轮」中的重复 system 组装 | 默认推荐 |
| B. 真回环 | `tools → agent`，受 `MAX_TOOL_ROUNDS` 约束；最后一轮才 stream | 确需多跳推理时 |

若选 A：清理无效的「round=2」语义或改为「语义补调最多 1 次」的明确计数。

**涉及文件**：`orchestrator.py`、`graph.py`、`policy.py`

---

#### P1-2 观测升级为 trace

**改动**

- 每轮请求生成 `trace_id`，贯穿 classify / effective_intent / force_tool / tool / scene / latency / token
- Langfuse：用 span 树替代裸 event（密钥齐全时）
- 可选：FastAPI / SQLAlchemy OTEL Instrumentor（`pyproject` 已有依赖）

**涉及文件**：`backend/app/agent/observe.py`、`chat_service.py`、`main.py`

---

#### P1-3 工具层有限重试

对瞬时失败（超时 / 5xx）重试 1 次；永久失败保持「不得编造」文案。覆盖 `search_official_data` 与 RAG 下游超时。

---

#### P1-4 黄金问评测最小集

将文档中的门禁场景做成 CI（mock 分类 + 工具）：

| 用例 | 期望 |
|---|---|
| 差旅补贴 / 公司制度 | 强制或实际调用为 `query_policy`，不强制外网 |
| 某省财政收入 | `search_official_data` |
| 官方查验入口 | 零工具 |
| 短追问「那一线城市呢」 | 继承 `last_intent` |
| 问候「你好」 | 不 `force_tool` |

RAG 侧另建 50～100 条租户 golden（可 fixture）：Recall@5、门槛通过率。路径建议：`backend/tests/eval_*`。

---

#### P1-5 实现或下线 interrupt API

`POST /interrupt/{session_id}` 与 `stream_persist` 断连能力对齐；做不到则删除接口并文档标明「仅客户端 aclose」。

---

#### P1-6 收敛发票 / 合同异步语义

| 选项 | 动作 |
|---|---|
| A | 正式接线 `process_invoice_ocr.delay` / 合同 Celery，前端轮询 processing 状态 |
| B | 删除或归档闲置 task，文档写明「同步 SSE 为主路径」 |

**禁止**长期双轨。合同侧同步做：强制 JSON `violations` + 条款锚点；弱化纯启发式 `guessRiskLevel`。

**涉及文件**：`tasks/ocr_task.py`、`tasks/contract_task.py`、`chat_service.py`、侧栏组件、清理 `contract_parse_pipeline_not_implemented` 残留文案。

---

#### P1-7 父块引用对齐（制度）

注入时保留命中子句高亮区，prompt 标明「命中条款 vs 上下文」，降低引用锚点漂移。依赖 P0-7。

---

### 4.3 P2 — 结构债 / 扩展

| ID | 改动 | 说明 |
|---|---|---|
| P2-1 | 附件子图收口 | 识别/审查 yield 进图节点，或明确「路由图 + 副作用在外」并删除 `_dispatch_upload` 双入口 |
| P2-2 | 统一上下文组装 | 主路径只保留 `assemble_context` + `attach_memory`；弱化重复 `SessionContext.load` 与遗留 `build_prompt` |
| P2-3 | 图内细化 status | 进入 tools 时区分「知识库 / 联网」 |
| P2-4 | `confirm_pending` 加强 HITL | 无侧栏字段修订时引导侧栏，避免 `fields=None` 直确认 |
| P2-5 | 工具注册表 + MCP 最小切片 | `TOOL_CATALOG` 支持「本地 \| MCP」；先只读检索 server；配置进 `tool_configs`；**真实 MCP 协议**，非文案 |
| P2-6 | 稀疏召回升级 | zhparser / jieba 或加权 BM25；限制 OR 噪声 |
| P2-7 | Milvus 标量索引 / 分区 | `tenant_id` / `doc_type` |
| P2-8 | Embedding 版本迁移 | 模型/维度变更一键全库 reindex + collection 版本名 |
| P2-9 | 用户反馈闭环 | 消息「有用/无用」→ dashboard 低分查询聚合 |
| P2-10 | 租户纵深 | 关键表 RLS 或强制 repository；全局文档上传强审计 |

---

## 5. 迭代计划

### 迭代 1 · 守门（约 1～1.5 周）

顺序建议：

1. P0-1 强制补调分化 + 改测  
2. P0-2 文档对齐  
3. P0-3 闲聊回归用例  
4. P0-4 JWT tenant  
5. P0-5 限流  
6. P0-6 metrics  
7. P0-7 制度 sources（前后端）  
8. P0-8 Rerank / 门槛  
9. P0-9 幽灵向量最小治理  

**里程碑**：制度问串源风险关闭；生产有限流与 metrics 保护；制度回答可展示来源。

### 迭代 2 · 变强（约 1～2 周）

1. P1-1 流式合并（先 ADR）  
2. P1-2 trace  
3. P1-3 工具重试  
4. P1-4 黄金问 CI  
5. P1-5 interrupt  
6. P1-6 Celery 收敛 + 合同 JSON violations  
7. P1-7 父块引用  

**里程碑**：延迟可感知下降；门禁用例进 CI；单据管道单一真相。

### 迭代 3 · 扩展（按需）

P2 按产品优先级抽取；建议先做 **P2-5 工具注册表（为 MCP 预留）** 与 **P2-9 反馈**，其余按规模再排。

---

## 6. 文件总表（便于拆 PR）

| 区域 | 主要路径 |
|---|---|
| Agent 门禁 / 图 | `backend/app/agent/graph.py`、`policy.py`、`orchestrator.py`、`tools/catalog.py`、`observe.py` |
| 鉴权 / 限流 | `backend/app/api/deps.py`、`core/security.py`、`core/rate_limit.py`（新建）、`main.py` |
| RAG | `services/rag_hybrid.py`、`kb_indexing.py`、`milvus_service.py`、rerank 相关 |
| 单据 | `services/chat_service.py`、`tasks/ocr_task.py`、`tasks/contract_task.py` |
| 前端 | `SearchSourcesBar.tsx`、`useSSE.ts`、合同/发票侧栏残留文案 |
| 文档 | `agent-langchain-langgraph.md`、`agent-b2.md`、`provide.md`、`deploy-production.md`、本文 |
| 测试 | `tests/test_agent_graph.py`、`test_agent_policy.py`、`test_rag_hybrid.py`、新建 `tests/eval_*` |

**PR 拆分建议**（小 PR、易审）：

1. `fix(agent): 制度意图强制补调优先知识库`  
2. `docs: 对齐 B1/B2 与闲聊工具策略`  
3. `fix(security): JWT tenant 校验 + 限流 + metrics`  
4. `feat(rag): 制度 sources SSE + 前端展示`  
5. `fix(rag): Rerank 与门槛解耦`  
6. 后续 P1 各自独立 PR  

---

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 改强制补调后公开追问漏调变制度 | 语义补调仍在；`PUBLIC_TAX` 默认外网；黄金问覆盖 |
| 限流误伤正常用户 | 先用现有配置默认值；管理端可调；日志打超限原因 |
| 制度 sources 字段变更破坏前端 | `kind` 可选字段向后兼容；旧客户端忽略未知字段 |
| 流式合并引入回归 | 保留图失败回退 A 管道；feature flag `agent_stream_after_tools` |

每项 P0 合并后保留一键回滚（单 PR revert）。

---

## 8. 验收清单（迭代 1 出门标准）

- [x] 制度类漏调 → 仅强制 `query_policy`（单测已改；待手工 3 问）
- [x] 公开财税漏调 → 仅强制 `search_official_data`（既有单测）
- [x] 问候不触发 `force_tool`（单测）
- [x] Agent 文档与代码无矛盾条款
- [x] 篡改 JWT `tenant_id` → 401（单测）
- [x] 超限流 → 429（单测）
- [x] `/metrics` 外网不可未认证访问（中间件；待部署侧配 token）
- [x] 制度问答 SSE 含 sources，前端可见（代码已接；待联调）
- [x] 弱相关批次不会因 min-max 全部通过 0.35（单测）

---

## 9. 附录：现状拓扑（便于对照改文档）

```text
POST /chat/stream
  ├─ 有附件 → upload_graph 分类 → ChatService 识别/审查（侧栏确认）
  └─ 无附件 → classify_intent → effective_intent
           → assemble_context
           → AgentOrchestrator.stream_text
                → text_chat_graph: gate → agent → tools → finalize
                → （可选）语义补调 / force_tool
                → stream_llm_and_persist + sources
```

工具白名单（当前）：

| Intent | 工具 |
|---|---|
| `policy_query` / `public_tax` / `chitchat` | `query_policy`, `search_official_data` |
| `official_portal` / 无附件单据 / `confirm_pending` | `[]` |

---

**文档维护**：实施过程中每完成一个 P0/P1 条目，在本文对应节将状态改为「已落地」并注明 PR / 日期；重大裁定变更同步改 §3。
