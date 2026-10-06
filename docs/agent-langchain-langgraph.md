# 文本 Agent 编排：LangChain + LangGraph 改动方案与测试验证

| 项 | 内容 |
|---|---|
| 状态 | 实施中（B1 代码已接入 ChatService 文本入口） |
| 范围 | B1：无附件文本对话 |
| 前置 | A 已落地：`classify_intent` + 既有业务管道 |
| 关联 | `docs/PRD.md` 能力路由与会话隔离；`docs/TD.md` §5 Agent 编排（本文替代其中的 AgentExecutor 示例） |

---

## 1. 背景与结论

当前线上文本路径由 `ChatService` 按 A 的意图分类进入：企业 RAG、权威站检索、门户引导、闲聊。附件仍走 `_dispatch_upload`（视觉分类 → 发票识别 / 合同审查）。

TD 原文使用 LangChain `AgentExecutor`。本方案改为：

- **LangChain**：模型适配、Tool schema、标准消息类型（Human / AI / Tool）。
- **LangGraph**：一次请求内的状态图（分类 → 白名单绑工具 → 模型步 → 工具步 → 结束）。
- **不使用** `create_tool_calling_agent` + `AgentExecutor`（与意图白名单冲突）。
- **Chat API / SSE 协议不变**；`ChatService` 仍是唯一入口。

**不做（本阶段）**：用图接管发票识别、合同审查、归档确认；多 Agent 互调；Langfuse；会话摘要与历史消息向量 RAG。

---

## 2. 目标与非目标

### 2.1 目标（B1）

1. 无附件文本：`classify_intent` → 按意图绑定允许的工具 → LangGraph 循环（最多 2 轮 Tool）→ 流式回复。
2. 只读工具仅两个：`query_policy`、`search_official_data`；`policy_query` / `public_tax` 均可调用二者。
3. A 的硬门禁保留：公司制度不搜外网冒充规定；公开财税以权威站为主并可叠加知识库；官方门户不调工具、不假装已查验；归档必须用户在侧栏确认。
4. 图失败或厂商不支持 function calling 时，回退现有 `_stream_text_intent`（A 管道）。
5. 首轮未调工具时软提醒一轮，**不**强制补调。

### 2.2 非目标

| 不做 | 原因 |
|---|---|
| 附件进 Graph | 侧栏、pending、人确认是有副作用的业务链 |
| `archive_invoice` / `ocr_invoice` 作为 Agent 工具 | 归档禁止由模型直接落库；现有 tools 骨架不可用 |
| Graph Checkpointer / 全局 memory | PRD：每次请求独立 SessionContext，请求结束销毁 |
| 替换 `llm_service.invoke` / `stream` | 视觉识别、连通性测试、意图分类继续走 LiteLLM |

---

## 3. 职责划分

| 层 | 负责 | 不负责 |
|---|---|---|
| LangChain | `ChatFinanceLLM`（包现有租户 LLM 配置）；`StructuredTool`；`HumanMessage` / `AIMessage` / `ToolMessage` | AgentExecutor、自由选工具 |
| LangGraph | `StateGraph`：classify、gate、agent、tools、finalize；`max_tool_rounds`；按意图裁剪 tools | 发票/合同子图（留 B2） |
| ChatService | 鉴权、消息落库、附件管道、把图事件转成现有 SSE | 文本路径上用关键字选知识源 |
| `llm_service` | 配置解析、视觉、分类、连通性、A 回退流式 | 不必在本层实现 tool 循环 |

依赖：`backend/pyproject.toml` 已有 `langchain`、`langchain-core`。**新增 `langgraph`**（版本与 langchain 0.3 兼容）。对话模型使用自写适配器调用 `complete_with_config` / 流式接口，保留 DashScope `enable_thinking: false` 等厂商差异，不绑死 `ChatOpenAI`。

---

## 4. 图拓扑

无附件、且意图需要「可调工具或闲聊生成」时进入下图。`official_portal`、无附件的 `invoice_upload` / `contract_upload` 可由 gate 短路到现有生成逻辑，不进入 tool 循环。

```
START
  → classify          # 复用 classify_intent（A）
  → gate              # 写入 allowed_tools；门户/无附件单据可短路
  → agent             # bind_tools(allowed) 后调用模型
  → route
       ├ 有合法 tool_calls 且 round < 2 → tools → agent
       └ 否则 → finalize → END
```

### 4.1 State

每次请求新建，禁止进程级全局 memory。

- `messages`：LangChain 消息列表  
- `intent` / `allowed_tools` / `tool_round`  
- `tenant_id`、`user_id`、`session_id`、`db` 放入 `config["configurable"]`，不写入可序列化、可持久化的 state  

B1 **不启用** Graph persist / checkpointer。

### 4.2 意图 → 工具白名单（写在代码里，不只写在 prompt）

| Intent | allowed_tools | 行为 |
|---|---|---|
| `policy_query` | `query_policy`, `search_official_data` | 默认偏知识库；可叠加官方；低分/空库不得用外网冒充公司制度 |
| `public_tax` | `query_policy`, `search_official_data` | 默认偏官方；可叠加知识库对照公司执行 |
| `official_portal` | `[]` | 只生成官方入口引导 |
| `chitchat` | `[]` | B1 闲聊不开放工具，避免乱搜 |
| `invoice_upload` | `[]` | 无附件：引导上传；有附件不进本图 |
| `contract_upload` | `[]` | 同上 |

工具节点二次校验：不在 `allowed_tools` 中的调用丢弃并打日志。首轮无合法 call 时软提醒一轮，不强制补调。

---

## 5. 工具设计

重写 `backend/app/agent/tools/`，删除或停用半残实现（空 bytes 的 `ocr_invoice`、占位 `archive_invoice` / `review_contract`）。

| 工具名 | 调用 | 返回 | 注意 |
|---|---|---|---|
| `query_policy` | `rag_service.retrieve`，相关分 `< 0.35` 视为未命中 | 片段标题+正文，或「知识库暂无相关规定」 | 注入 `tenant_id`；不发外网 |
| `search_official_data` | `official_policy_service.search_and_fetch`（支持 region/period/topic）+ `format_official_policy_context` | 已格式化的权威资料（含失败「不得编造」） | 不在工具内直接写 SSE；由 Graph 在进入该节点时发 `status` |

不提供发票真伪 / 工商公示 / 裁判文书查询工具。

---

## 6. SSE 映射

前端契约保持不变（见 `backend/app/api/v1/chat.py`、`frontend/src/hooks/useSSE.ts`）。

| 图侧事件 | SSE |
|---|---|
| 进入双源检索 | `{type: "status", message: "正在检索企业制度与权威网站…"}` |
| 进入 `query_policy` | `{type: "status", message: "正在检索企业制度…"}` |
| 模型文本流 | `{type: "text", content}` |
| 异常 | `{type: "error", message}` |
| 正常结束 | `{type: "done"}` |

工具原始 JSON 不得作为 `text` 推给用户。`sidepanel` 仅由附件管道发出。助手消息可继续写入 `tool_calls` 检索 trace（与现网 `search_official_policy` 结构对齐）。

---

## 7. 文件改动清单

| 路径 | 动作 |
|---|---|
| `backend/pyproject.toml` | 增加 `langgraph` |
| `backend/app/agent/llm_adapter.py` | 新增：`ChatFinanceLLM`，scene / tenant / db |
| `backend/app/agent/policy.py` | 新增：`tools_for_intent(intent)` |
| `backend/app/agent/tools/` | 重写只读工具；去掉归档/空识别骨架 |
| `backend/app/agent/graph.py` | 新增：编译 `text_chat_graph` |
| `backend/app/agent/orchestrator.py` | 改为 `stream_text()`：跑图并将事件转为 SSE dict |
| `backend/app/services/chat_service.py` | 无附件分支改调 `orchestrator.stream_text`；附件逻辑不动 |
| `backend/app/api/v1/chat.py` | 仅更新注释 |
| `backend/tests/` | 见第 9 节 |
| `docs/TD.md` | 实施时将 §5.2 AgentExecutor 示例改为指向本文（可另提交） |

`backend/app/agent/memory/summary.py`、`entities.py`：B1 不接入图。

---

## 8. 实施顺序

1. **适配器 + 两个 StructuredTool + `tools_for_intent`**，单测不编译图、不改 ChatService。  
2. **编译 StateGraph + `orchestrator.stream_text`**，ChatService 文本入口切换。门户 / 无附件单据可短路到现有生成，避免图过大。  
3. **回退**：图初始化失败、模型不返回 tool_calls、tool 轮次超限 → `_stream_text_intent`。回退是上线条件。

---

## 9. 测试验证方案

### 9.1 原则

- 默认 mock LLM / RAG / 检索，不启后端进程、不打真实厂商（与仓库「不自动启动项目」约定一致）。  
- 行为与 A 对齐：来源正确、不串库、SSE 类型不扩。  
- 附件回归证明 Graph 未接管单据链。

### 9.2 单测：白名单

文件建议：`backend/tests/test_agent_policy.py`。

| 用例 | 期望 |
|---|---|
| `policy_query` / `public_tax` | `query_policy` + `search_official_data` |
| `official_portal` / `chitchat` / 无附件发票或合同 | 空列表 |

### 9.3 单测：工具

文件建议：`backend/tests/test_agent_tools.py`。

| 用例 | 期望 |
|---|---|
| RAG 高分命中 | 返回含标题与正文 |
| RAG 空或 `score < 0.35` | 「知识库暂无」；不含 chinatax / mof 域名 |
| 搜索成功 | 返回格式化资料，含标题与允许的 URL |
| 搜索失败 | 文案含「不得编造」 |

### 9.4 单测：LLM 适配器

文件建议：`backend/tests/test_agent_llm_adapter.py`。

| 用例 | 期望 |
|---|---|
| 纯文本 complete | 得到 `AIMessage.content` |
| 底层返回 OpenAI 风格 `tool_calls` | 填入 `AIMessage.tool_calls` |
| DashScope 配置 | 仍关闭 thinking（与现网一致） |

### 9.5 单测：LangGraph

文件建议：`backend/tests/test_agent_graph.py`。用固定 `intent` + mock 模型/工具，调用 `ainvoke` 或收集 `astream` 事件。

| 编号 | 给定 | 期望 |
|---|---|---|
| G1 | `policy_query` + 模型调 `query_policy` + RAG 高分 | 执行知识库；最终文本含制度片段 |
| G2 | `policy_query` + 首轮无 call | 软提醒一轮；仍无 call 则空工具结果，不 force |
| G3 | `public_tax` + 模型调 `search_official_data` | 执行搜索；事件含 `status`；落库 `tool_calls.tool == search_official_data` |
| G4 | `official_portal` | 工具次数 = 0；回复含查验/公示/文书/12366 URL |
| G5 | `policy_query` + 模型调官方工具 | 允许执行（双源白名单） |
| G6 | 同轮双工具合法 call | 两者均执行 |
| G7 | `contract_upload` 无附件 | 不进工具；引导上传 |
| G8 | adapter 抛错 | 回退 A 管道；仍有 `error` 或完整 `text`+`done`；进程不崩 |

### 9.6 回归：现有流式与意图

保留并调整 patch 点：

- `backend/tests/test_intent_router.py`：分类 JSON / 低置信度 / 演示回退，行为不变。  
- `backend/tests/test_public_tax_search.py`：启发回退与 URL 白名单，行为不变。  
- `backend/tests/test_chat_streaming.py`：  
  - 公开财税：仍断言 `status`、权威 URL、`tool_calls`；mock 改为工具或 `official_policy_service`。  
  - 制度 RAG 注入、无附件发票引导、自定义 `system_prompt`、LLM 错误事件：入口改 Graph 后断言仍成立。

### 9.7 回归：附件（证明未进 Graph）

| 用例 | 期望 |
|---|---|
| 专票图 +「识别这个合同」 | 发票侧栏 + 口误纠正提示（`_user_type_mismatch_instruction`） |
| 合同 PDF | 合同侧栏 `pending_review`，不自动 `active` |
| 文件不可读 | `error`，不触发公开检索 |

继续 mock `invoice_vision_service.classify`，不依赖真实视觉模型。

### 9.8 契约与前端

| 检查项 | 标准 |
|---|---|
| SSE 类型集合 | 仅 `text` / `status` / `sidepanel` / `done` / `error` |
| `useSSE.ts` | B1 不强制改接口；`status` 已有则只确认文案展示 |
| 手工冒烟（有密钥环境） | 制度、公开财税、门户、闲聊、上传发票各 1 条 |

### 9.9 厂商矩阵（手工，可选）

租户已配置 Key 时，各跑 1 条 `public_tax` + 1 条 `policy_query`：

- DeepSeek  
- 通义（thinking 关闭）  
- 其他 OpenAI 兼容  

判定：

- 能产出合法 `tool_calls` 且白名单命中 → 通过。  
- 不能 tool、自动回退 A 且来源仍正确 → **降级通过**。  
- 制度问题打到外网，或门户假装已查验 → **失败**。

### 9.10 黄金问（建议 15 条，CI 可 mock 分类+工具）

语义必须人工抽检过至少一轮：

1. 「差旅住宿补贴怎么报」→ 知识库，不搜税务总局。  
2. 「广州企业所得税优惠」→ 权威检索，不锁空制度。  
3. 「帮我查验发票真伪」→ 无工具，给出 `https://inv-veri.chinatax.gov.cn`。  
4. 「今天天气」→ 无工具。  
5. 口称合同的发票图片 → 附件链，不进公开检索。

其余条目可从现有 `test_public_tax_search` / 制度问答用例扩展。

---

## 10. 风险与验收标准

| 风险 | 缓解 |
|---|---|
| 延迟增加 1～2 个 LLM RTT | `status` 事件；`max_tool_rounds = 2` |
| 分类意图与模型想调的工具冲突 | 以 `allowed_tools` 为准，非法 call 丢弃 |
| db / 密钥进入 Graph 持久化 | B1 无 checkpointer；敏感对象只放 configurable |
| 文档与代码再分叉 | 实施后更新 TD §5，指向本文 |

**B1 完成标准**

1. 无附件文本走 LangGraph；附件走 `stream_upload` 子图，识别/审查实现仍是 ChatService 原函数。  
2. 第 9.2～9.6 节单测与回归通过。  
3. 公开财税 / 企业制度 / 官方门户三条路径的来源与 A 等价（不串库）。  
4. 不支持 tools 的配置自动回退 A，对话不中断。  
5. 前端无需为 B1 改 SSE 事件类型。

---

## 11. 与 B2 的边界

B2 方案见 **[docs/agent-b2.md](agent-b2.md)**，**已实施**：

- B2-1 会话摘要 / pending 实体  
- B2-2 短追问继承白名单  
- B2-3 附件子图（`classify_file` → invoice / contract / file_chat），归档仍走侧栏 REST 或对话 `confirm_pending`（同一 `confirm` service）  
- B2-4 可选 Langfuse：无公钥+私钥时不上报  

B2 **没有**把归档做成模型 Tool，也没有用 Graph interrupt 替换确认归档 API。历史消息全量向量 RAG、多 Agent 不在 B2。
