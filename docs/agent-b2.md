# B2 方案：会话记忆、追问继承与单据子图

| 项 | 内容 |
|---|---|
| 状态 | B2-1 / B2-2 已落地；B2-3 单据子图、B2-4 Langfuse 未做 |
| 前置 | B1 已落地：无附件文本走 LangGraph + 意图白名单；附件仍 `_dispatch_upload` |
| 关联 | [B1 文档](agent-langchain-langgraph.md)；`docs/PRD.md` §6 四层上下文；`docs/TD.md` §5 / §6 |
| 原则 | 归档必须人确认；Agent 不持全局状态；不引入 `archive_*` 工具 |

---

## 1. 为什么要做 B2

B1 解决的是**单轮选对工具**。PRD 里尚未交付、且用户会立刻碰到的缺口是：

1. **长会话失忆**：只带最近 20 条原文，没有摘要 / 待办实体；「上次那张发票」无法稳定召回。  
2. **追问掉白名单**：上一轮是制度问答，用户说「那一线城市呢？」可能被分类成闲聊，B1 闲聊无工具，模型容易编。  
3. **单据与文本两套编排**：识别/审查仍在 ChatService 长函数里，图无法表达「识别 → 等人确认 → 归档」的产品状态（确认本身已经在侧栏 REST 完成，缺的是**会话级 pending 记忆**）。  
4. **可观测**：多一次分类 + 工具，出问题难对齐 Langfuse / 现有日志。

B2 **不是**上多 Agent，也不是把侧栏确认改成 LangGraph `interrupt` 硬替代（见 §4.3）。

---

## 2. 目标与非目标

### 2.1 目标（按切片，必须按序）

| 切片 | 目标 | 用户可感知结果 |
|---|---|---|
| **B2-1 记忆** | 每次请求 `SessionContext.load`；system 注入摘要 + pending；每 10 轮滚摘要；识别/审查成功写实体 | 同一会话里能提到「刚才那张票 / 待归档合同」 |
| **B2-2 追问** | `session_memory.last_intent` + 短追问检测；继承上一轮白名单再进图 | 「那一线城市呢」仍走知识库，不搜外网 |
| **B2-3 单据子图** | 把 `_dispatch_upload` 收成图节点（识别 / 审查 / 文件闲聊），**归档仍走现有确认 API** | 编排可读、可测；行为与现网侧栏一致 |
| **B2-4 观测** | 可选 Langfuse：分类、工具名、强制补调、scene | 后台能看到一轮里调了哪个工具 |

### 2.2 非目标（B2 明确不做）

| 不做 | 原因 |
|---|---|
| `archive_invoice` / `archive_contract` 作为模型可调 Tool | 模型会在用户未点确认时落库 |
| 用 LangGraph Checkpointer 跨进程打断、等侧栏按钮 resume | 确认已是独立 HTTP；把 SSE 线程和侧栏绑死会双写状态 |
| 闲聊默认开放两个只读工具 | 等于取消分类器，制度/外网会串 |
| 历史消息全量向量 RAG（PRD 第四层） | 工作量大、与会话摘要重叠；放到 B3 |
| Supervisor 多 Agent、发票/合同各一个运行中的 Agent 进程 | 过重；子图节点即可 |
| 替换视觉识别 / 合同抽正文实现 | 只搬编排，不改识别质量 |

---

## 3. 与 B1 的衔接（必须保持）

- 意图枚举与 `tools_for_intent` 仍是硬门禁；B2 只**增加** `followup` 解析，不删白名单。  
- 无附件主图拓扑不变：`gate → agent → tools → finalize` → `llm_service.stream`。  
- 非法 tool 丢弃、空库「知识库暂无」、门户零工具、公开财税强制检索。  
- Chat API / SSE 事件类型默认不变；B2-1 不新增事件。B2-4 不把 trace 推给用户。

---

## 4. 切片设计

### 4.1 B2-1 会话记忆（优先）

**现状**：`SessionContext`、`sessions.summary`、`session_memory` 表、`memory/summary.py` / `entities.py` 均为骨架，Chat 主路径未调用。

**做法**：

1. 每次 `stream_response` 开头 `ctx = await SessionContext.load(...)`，请求结束丢弃，禁止模块级 cache。  
2. `history_to_messages` / `_opening_prompt` 的 system 增加固定块：

```
[会话摘要]
{summary 或「（无）」}

[当前状态]
pending_task: {invoice_pending | contract_pending | none}
pending_ids: ...
```

3. **摘要**：`len(messages) % 10 == 0`（或本轮结束后条数达 10 的倍数）异步/await 调用现有 `update_summary`，写入 `sessions.summary`；失败只打日志，不影响本轮 SSE。  
4. **实体（规则为主，LLM 为辅）**：  
   - 发票 `create_pending` 成功 → `uploaded_invoices` 追加 id，`pending_task=invoice_pending`  
   - 合同 `create_pending` 成功 → 同上 `contract_pending`  
   - 确认归档 API 成功 → 清掉对应 pending，保留 id 列表  
   - 制度命中 → `queried_policies` 记文档标题  
   不在每一轮对闲聊跑实体 LLM，避免延迟和胡抽。  
5. `SessionContext.build_prompt` 与 MoFan `system_prompt` **合并**：用户配置的人设在前，记忆块在后，避免冲掉品牌提示。

**不引入** Postgres checkpointer。记忆只在 Postgres 业务表。

### 4.2 B2-2 追问继承白名单

**问题**：分类器看到短句「一线城市呢 / 那税率呢 / 继续」会标 `chitchat`。

**做法**（代码门禁，不只靠 prompt）：

1. 实体增加 `last_intent`（上一轮最终采用的 Intent）。  
2. 若本轮 `classify_intent` 为 `chitchat` **且** 文本像追问，则 `effective_intent = last_intent`（仅当 last 为 `policy_query` 或 `public_tax`）。  
3. 追问启发（可放 `heuristics.py`）：过短（如 &lt; 20 字）、指示代词/省略（那 / 这个 / 还有呢 / 一线 / 二线 / 具体标准）、或无新领域词。  
4. 若 last 是 `official_portal` / 单据意图，不继承（避免把「好的」变成再识别一次）。  
5. `chitchat` **仍然默认无工具**；只有继承后才带上一轮白名单进图。

**不采用**：闲聊绑两个工具让模型自己选。

### 4.3 B2-3 单据子图（编排搬迁，确认机制不换）

**现状**：附件在 `_dispatch_upload`：视觉分类 → 发票识别 / 合同审查 / 文件闲聊；归档是侧栏点确认 → REST。这已经是「人确认中断」，只是中断点在 HTTP，不在 Graph。

**推荐拓扑**（父图按有无附件分支）：

```
START
  → has_file?
       ├ 否 → 文本图（B1 + B2-1/2）
       └ 是 → classify_file
              → invoice_node | contract_node | file_chat_node
              → write_entities
              → END
```

- `invoice_node` / `contract_node` **调用现有** `_stream_invoice_recognize` / `_stream_contract_review`（或抽成 service 函数），继续 yield 现有 `sidepanel` / `text`。  
- **不**把识别做成模型可选 Tool（避免漏调、重复视觉）。分类结果直接进对应节点。  
- **不**在图内 `interrupt()` 等侧栏。确认归档继续走已有 `confirm` 接口；该接口成功后更新 `session_memory`（B2-1）。  
- 用户在对话里发「确认归档 / 帮我存进去」：新增意图 `confirm_pending`（分类器 + 有 pending 实体才生效）→ **调用与 REST 相同的 service**，不新写一套入库。无 pending 则口头说明去点侧栏。

为何不用 LangGraph interrupt 替代侧栏：

- 确认发生在**另一次 HTTP**，与识别 SSE 不是同一 runnable。  
- Checkpointer 要持久化 thread_id、且不能把 `db` session 序列化进去。  
- 产品已有 pending_review + 去重 + 审计；Graph resume 容易和 REST 双入口打架。

若未来要「同一条 SSE 里识别完立刻问是否归档再等用户」，单独立项 B3，再考虑 interrupt + 前端第二段 stream。

口误纠正（「识别这个合同」实为发票）仍用现有 `_user_type_mismatch_instruction`，挂在 `invoice_node` 回复提示，不放进 Tool。

### 4.4 B2-4 Langfuse（可选、可关）

- 环境变量关闭时零依赖行为。  
- span：`classify_intent`、`effective_intent`、强制补调、tool name、scene、tenant_id（不要把票据全文默认上传，或截断）。  
- 不替代现有 structlog。  
- 不作为 B2-1～3 的上线门槛。

---

## 5. 文件改动预估

| 路径 | 切片 | 动作 |
|---|---|---|
| `app/agent/context.py` | B2-1 | `load` 接 Chat 主路径；`build_memory_block()` |
| `app/agent/memory/summary.py` | B2-1 | 接 `sessions.summary` 读写 |
| `app/agent/memory/entities.py` | B2-1 | 规则 merge，少用 LLM |
| `app/agent/heuristics.py` | B2-2 | `looks_like_followup` |
| `app/agent/policy.py` | B2-2 | `effective_intent(classified, last, text)` |
| `app/agent/orchestrator.py` | B2-1/2 | opening system 拼记忆块 |
| `app/agent/graph.py` | B2-3 | 可选父图 `has_file` 分支；或 ChatService 内组子图 |
| `app/services/chat_service.py` | B2-1/3 | load ctx；上传成功写实体；子图替换 `_dispatch_upload` 外壳 |
| 发票/合同 confirm API | B2-1 | 成功后清 pending |
| `app/agent/router.py` | B2-3 | 可选 `confirm_pending` |
| 测试 | 全部 | 见 §7 |
| `docs/TD.md` §6 | B2-1 | 标明已接线，避免再写骨架当现状 |

B2-1 不改前端。B2-3 不改 SSE 类型则前端可不改。

---

## 6. 实施顺序

1. **B2-1**：load / 注入 / 摘要 / 实体，行为测试不依赖 Langfuse。  
2. **B2-2**：追问继承，黄金句「差旅怎么报」→「一线城市呢」。  
3. **B2-3**：父图或函数级子图包装附件链 + `confirm_pending` 走原 service。  
4. **B2-4**：env 开关，默认可关。

禁止并行做 interrupt + 记忆，状态模型会乱。

---

## 7. 测试验证方案

### 7.1 B2-1

| 用例 | 期望 |
|---|---|
| 新会话无摘要 | system 含「（无）」或空块，不报错 |
| 第 10 轮结束 | `sessions.summary` 非空（mock LLM） |
| 发票 pending 写入 | 实体有 invoice id 与 `invoice_pending` |
| 确认归档 | pending 清除，id 仍在已上传列表 |
| 切换 session_id | 绝不读到另一会话 summary |
| 摘要 LLM 失败 | 本轮仍能 `text`+`done` |

### 7.2 B2-2

| 用例 | 期望 |
|---|---|
| last=`policy_query` +「一线城市呢」 | 只调 `query_policy` |
| last=`public_tax` +「那最新税率呢」 | 只调搜索 |
| last=`policy_query` +「广州企业所得税优惠」 | **不继承**，走 `public_tax`（分类器优先于追问） |
| last=`invoice_upload` +「好的」 | 不继承、不二次识别 |
| 无 last 的短闲聊 | 无工具 |

分类器与追问冲突时：**本轮分类若为 policy_query / public_tax / portal / 单据，以本轮为准。** 仅 `chitchat` 才考虑继承。

### 7.3 B2-3

| 用例 | 期望 |
|---|---|
| 专票 +「识别这个合同」 | 发票侧栏 + 口误纠正；不进公开检索 |
| 合同 PDF | pending_review，不 `active` |
| 对话「确认归档」且有 pending | 与 REST confirm 同一 service，审计仍在 |
| 无 pending 时说确认 | 不写库，提示用侧栏 |
| 模型即使 hallucinate 归档 | 无 archive Tool，库状态不变 |

### 7.4 B2-4

无 Key 时测试不创建 span。有 Key 时单测 mock client，断言工具名标签存在。

### 7.5 回归（B1 黄金问必须全绿）

差旅制度、广州优惠、查验真伪、天气、口误发票图。附件回归不进文本工具。

---

## 8. 风险

| 风险 | 缓解 |
|---|---|
| 摘要污染人设 | 记忆块后置、长度上限 200 字 |
| 追问误继承到外网 | 仅 chitchat 可继承；本轮明确意图优先；portal/单据不继承 |
| 实体 LLM 乱写 pending | B2-1 只用识别/确认链路的规则写入 |
| 子图变成「识别 Tool」被跳过 | 文件分类结果硬路由节点，不 bind 给模型 |
| Checkpointer 泄漏 Session | B2 不启用；记忆只在业务表 |

---

## 9. 验收标准

**B2-1 完成**：Chat 主路径有 SessionContext；摘要按轮次更新；pending 与确认闭环；会话隔离测试通过。  

**B2-2 完成**：§7.2 表全绿；B1 黄金问不回退。  

**B2-3 完成**：附件行为与现网一致；对话确认与 REST 共用 service；**零** archive Tool。  

**B2-4 完成**：可关；不影响关闭时延迟与测试。  

全部切片完成后，更新 `docs/agent-langchain-langgraph.md` §11 与本文状态为「已实施」。

---

## 10. 建议的第一件事

落地从 **B2-1** 开始：接线 `SessionContext.load` + 记忆块注入 + 发票/合同 pending 实体。不先做 Langfuse，也不先做 Graph interrupt。
