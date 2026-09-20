# 企业 AI Agent 财务智能与单据处理平台

## 技术选型与架构设计文档

**版本**：V1.0
**阶段**：私有化单企业部署，预留 SaaS 多租户升级
**日期**：2026-09-20
**技术栈**：React + shadcn/ui + TailwindCSS + SSE / FastAPI / LangChain

---

## 目录

1. 选型原则
2. 总体架构
3. 前端技术方案
4. 后端技术方案
5. Agent 编排方案
6. 多轮对话与会话隔离实现
7. OCR 方案
8. 合同审查方案
9. RAG 方案
10. LLM 网关方案
11. 数据存储方案
12. 安全方案
13. 部署方案
14. 多租户演进设计
15. 性能与可观测性
16. 成本估算
17. 技术风险与应对

---

## 1. 选型原则

- 私有化单企业部署优先，预留 SaaS 多租户
- 敏感数据不出域，外部 API 需脱敏
- 成本可控，MVP 阶段不追求过度架构
- 技术栈主流，社区活跃，易于招聘
- 前后端分离，流式交互优先

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────┐
│  前端（React + shadcn/ui + TailwindCSS）             │
│  Chat 界面 | 会话列表 | 侧弹窗 | 后台管理             │
│  流式：SSE                                           │
├─────────────────────────────────────────────────────┤
│  API 层（FastAPI）                                   │
│  认证 | 路由 | 校验 | SessionContext 创建             │
├─────────────────────────────────────────────────────┤
│  Agent 编排层（LangChain）                           │
│  意图识别 → 路由 → Tool 调用 → 流式输出               │
├─────────────────────────────────────────────────────┤
│  能力层                                              │
│  OCR | 合同解析 | RAG | LLM 网关                     │
├─────────────────────────────────────────────────────┤
│  数据层                                              │
│  PostgreSQL + pgvector | Redis | MinIO               │
├─────────────────────────────────────────────────────┤
│  基础设施                                            │
│  Docker | Nginx | Prometheus | Grafana | Loki        │
└─────────────────────────────────────────────────────┘
```

**数据流**：
```
用户输入 → React 前端 → FastAPI → LangChain Agent
  → 意图识别 → Tool 调用（OCR/RAG/LLM）
  → SSE 流式返回 → 前端渲染
  → 异步任务（OCR/合同审查）→ 写回 session → WebSocket 通知
```

---

## 3. 前端技术方案

### 3.1 技术栈

| 项 | 选型 | 理由 |
|---|---|---|
| 框架 | React 18 + TypeScript | 生态成熟，类型安全 |
| UI 组件 | shadcn/ui | 可定制，无锁定，基于 Radix |
| 样式 | TailwindCSS 3 | 原子化，开发快 |
| 状态管理 | Zustand | 轻量，适合会话状态 |
| 路由 | React Router 6 | 标准方案 |
| 请求 | Axios + React Query | 缓存、重试、错误处理 |
| 流式 | SSE（EventSource / fetch-stream） | Agent 流式输出 |
| 表单 | React Hook Form + Zod | 侧弹窗字段校验 |
| 图标 | Lucide React | shadcn 默认 |
| 构建 | Vite | 快 |
| 代码规范 | ESLint + Prettier | 标准 |

### 3.2 目录结构

```
src/
├── components/
│   ├── ui/                    # shadcn/ui 组件
│   ├── chat/
│   │   ├── ChatWindow.tsx     # 消息流
│   │   ├── MessageBubble.tsx  # 消息气泡
│   │   ├── InputBox.tsx       # 输入框 + 上传
│   │   ├── SessionList.tsx    # 会话列表
│   │   └── StreamRenderer.tsx # SSE 流式渲染
│   ├── sidepanel/
│   │   ├── InvoicePanel.tsx   # 发票侧弹窗
│   │   ├── ContractPanel.tsx  # 合同侧弹窗
│   │   └── RiskBadge.tsx      # 风险等级
│   └── admin/
│       ├── Dashboard.tsx
│       ├── InvoiceArchive.tsx
│       ├── ContractArchive.tsx
│       ├── KnowledgeBase.tsx
│       ├── UserManage.tsx
│       └── LLMSettings.tsx
├── pages/
│   ├── Login.tsx
│   ├── Chat.tsx
│   └── Admin.tsx
├── stores/
│   ├── sessionStore.ts        # 会话状态
│   ├── authStore.ts           # 认证状态
│   └── uiStore.ts             # UI 状态
├── api/
│   ├── client.ts              # Axios 实例
│   ├── chat.ts                # 聊天 API
│   ├── invoice.ts             # 发票 API
│   ├── contract.ts            # 合同 API
│   └── admin.ts               # 后台 API
├── hooks/
│   ├── useSSE.ts              # SSE Hook
│   ├── useSession.ts          # 会话 Hook
│   └── useAuth.ts             # 认证 Hook
├── lib/
│   ├── utils.ts
│   └── validators.ts          # Zod schemas
└── types/
    └── index.ts               # TS 类型定义
```

### 3.3 关键组件设计

#### 3.3.1 Chat 主界面

```tsx
// pages/Chat.tsx
export default function Chat() {
  const { sessions, currentSessionId, switchSession } = useSessionStore();
  
  return (
    <div className="flex h-screen">
      <SessionList
        sessions={sessions}
        currentId={currentSessionId}
        onSwitch={switchSession}
      />
      <div className="flex-1 flex flex-col">
        <ChatWindow sessionId={currentSessionId} />
        <InputBox sessionId={currentSessionId} />
      </div>
      <SidePanel />
    </div>
  );
}
```

#### 3.3.2 SSE 流式 Hook

```tsx
// hooks/useSSE.ts
export function useSSE(sessionId: string) {
  const [streaming, setStreaming] = useState(false);
  const [content, setContent] = useState('');
  
  const send = async (message: string, file?: File) => {
    setStreaming(true);
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('message', message);
    if (file) formData.append('file', file);
    
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      body: formData,
      headers: { Authorization: `Bearer ${token}` },
    });
    
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
      const { done, value } = await reader!.read();
      if (done) break;
      const chunk = decoder.decode(value);
      // 解析 SSE 格式：data: {...}\n\n
      const lines = chunk.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'text') setContent(prev => prev + data.content);
          if (data.type === 'sidepanel') openSidePanel(data.payload);
          if (data.type === 'done') setStreaming(false);
        }
      }
    }
  };
  
  return { send, streaming, content };
}
```

#### 3.3.3 发票侧弹窗

```tsx
// components/sidepanel/InvoicePanel.tsx
export function InvoicePanel({ invoice, onConfirm, onCancel }) {
  const form = useForm({
    resolver: zodResolver(invoiceSchema),
    defaultValues: invoice,
  });
  
  return (
    <Sheet open onOpenChange={onCancel}>
      <SheetContent className="w-[500px] sm:max-w-[500px]">
        <SheetHeader>
          <SheetTitle>发票识别结果</SheetTitle>
        </SheetHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onConfirm)} className="space-y-4">
            <FormField name="抬头" label="发票抬头" />
            <FormField name="公司" label="公司名称" />
            <FormField name="税号" label="税号" />
            <FormField name="金额" label="金额（含税）" type="number" />
            {/* ... 其他字段 */}
            <div className="flex gap-2">
              <Button type="submit">确定归档</Button>
              <Button variant="outline" onClick={onCancel}>取消</Button>
              <Button variant="ghost" onClick={onReOcr}>重新识别</Button>
            </div>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
```

### 3.4 会话状态管理（Zustand）

```ts
// stores/sessionStore.ts
interface SessionState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Record<string, Message[]>;  // 按 session 隔离
  switchSession: (id: string) => void;
  addMessage: (sessionId: string, msg: Message) => void;
  clearSession: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: {},
  
  switchSession: (id) => {
    set({ currentSessionId: id });
    // 若该 session 消息未加载，从后端拉取
    if (!get().messages[id]) {
      fetchMessages(id).then(msgs => {
        set(state => ({
          messages: { ...state.messages, [id]: msgs }
        }));
      });
    }
  },
  
  addMessage: (sessionId, msg) => set(state => ({
    messages: {
      ...state.messages,
      [sessionId]: [...(state.messages[sessionId] || []), msg]
    }
  })),
  
  clearSession: (id) => set(state => {
    const { [id]: _, ...rest } = state.messages;
    return { messages: rest };
  }),
}));
```

**关键**：消息按 `sessionId` 分组存储，切换会话时只渲染当前 session 的消息，从状态层就隔离。

### 3.5 后台管理端

- 独立路由 `/admin/*`，通过 `window.open('/admin', '_blank')` 新窗口打开
- 复用 shadcn/ui 组件，布局用 `Sidebar + Content`
- 表格用 `@tanstack/react-table` + shadcn Table
- 图表用 `Recharts`

---

## 4. 后端技术方案

### 4.1 技术栈

| 项 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.11 | AI 生态最强 |
| 框架 | FastAPI | 异步、高性能、自动文档 |
| ORM | SQLAlchemy 2.0 + Alembic | 成熟，迁移方便 |
| 校验 | Pydantic v2 | FastAPI 原生 |
| 任务队列 | Celery + Redis | OCR/合同审查异步 |
| 认证 | JWT + OAuth2 | 标准 |
| 流式 | SSE（StreamingResponse） | 轻量，兼容好 |
| 文件上传 | python-multipart + 分片 | 大文件支持 |
| 日志 | structlog | 结构化日志 |

### 4.2 目录结构

```
app/
├── main.py                    # FastAPI 入口
├── config.py                  # 配置
├── deps.py                    # 依赖注入
├── api/
│   ├── v1/
│   │   ├── auth.py            # 登录
│   │   ├── chat.py            # 聊天 + SSE
│   │   ├── sessions.py        # 会话管理
│   │   ├── invoices.py        # 发票
│   │   ├── contracts.py       # 合同
│   │   ├── kb.py              # 知识库
│   │   ├── users.py           # 用户管理
│   │   └── llm.py             # LLM 设置
├── agent/
│   ├── orchestrator.py        # LangChain Agent 编排
│   ├── context.py             # SessionContext
│   ├── router.py              # 意图识别路由
│   ├── tools/
│   │   ├── ocr_tool.py
│   │   ├── contract_tool.py
│   │   ├── rag_tool.py
│   │   └── archive_tool.py
│   └── memory/
│       ├── summary.py         # 摘要更新
│       └── entities.py        # 实体抽取
├── services/
│   ├── ocr_service.py
│   ├── contract_service.py
│   ├── rag_service.py
│   ├── llm_service.py
│   └── storage_service.py     # MinIO
├── models/                    # SQLAlchemy 模型
├── schemas/                   # Pydantic 模型
├── core/
│   ├── security.py            # JWT、加密
│   └── exceptions.py
└── tasks/                     # Celery 任务
    ├── ocr_task.py
    └── contract_task.py
```

### 4.3 SSE 流式接口

```python
# api/v1/chat.py
from fastapi import APIRouter, Depends, UploadFile, Form
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

@router.post("/chat/stream")
async def chat_stream(
    session_id: str = Form(...),
    message: str = Form(...),
    file: UploadFile | None = None,
    user = Depends(get_current_user),
):
    # 1. 校验 session 归属
    session = await verify_session(session_id, user.id, user.tenant_id)
    
    # 2. 创建独立 SessionContext
    ctx = await SessionContext.load(session_id, user.id, user.tenant_id)
    
    # 3. 文件处理（异步触发 OCR）
    if file:
        task = ocr_task.delay(session_id, file.filename, await file.read())
        # 先返回文件已接收消息
        ...
    
    # 4. Agent 流式处理
    async def event_generator():
        try:
            async for chunk in agent_orchestrator.stream(ctx, message):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 不缓冲
        },
    )
```

### 4.4 SessionContext 实现

```python
# agent/context.py
class SessionContext:
    def __init__(self, session_id: str, user_id: str, tenant_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.recent_messages: list[dict] = []
        self.summary: str = ""
        self.entities: dict = {}
        self.pending_task: str | None = None
    
    @classmethod
    async def load(cls, session_id, user_id, tenant_id):
        ctx = cls(session_id, user_id, tenant_id)
        # 加载最近 N 轮消息
        ctx.recent_messages = await get_recent_messages(session_id, limit=20)
        # 加载摘要
        ctx.summary = await get_summary(session_id)
        # 加载结构化记忆
        ctx.entities = await get_entities(session_id)
        ctx.pending_task = ctx.entities.get("pending_task")
        return ctx
    
    def build_prompt(self, user_input: str, rag_snippets: list[str]) -> list[dict]:
        system = f"""你是企业财务AI助手。

[会话摘要]
{self.summary}

[当前状态]
待确认任务：{self.pending_task}
已上传单据：{self.entities.get('uploaded_invoices', [])}

[相关历史]
{chr(10).join(rag_snippets)}
"""
        return [
            {"role": "system", "content": system},
            *self.recent_messages[-20:],
            {"role": "user", "content": user_input},
        ]
    
    async def append(self, message: dict):
        self.recent_messages.append(message)
        await save_message(self.session_id, message)
        # 每 N 轮触发摘要更新
        if len(self.recent_messages) % 10 == 0:
            await update_summary(self.session_id)
```

**关键**：每次请求创建独立的 SessionContext，请求结束销毁，**不持有全局状态**。

---

## 5. Agent 编排方案（LangChain）

### 5.1 技术栈

| 项 | 选型 | 理由 |
|---|---|---|
| 编排框架 | LangChain 0.3+ | 生态成熟 |
| 意图识别 | LangChain + Few-shot | 简单有效 |
| Tool 调用 | LangChain Tool / Function Calling | 标准 |
| 流式 | LangChain Streaming | 原生支持 |
| 可观测 | Langfuse | 调试与追踪 |

### 5.2 Agent 架构

```python
# agent/orchestrator.py
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

class AgentOrchestrator:
    def __init__(self, llm_service, tools):
        self.llm_service = llm_service
        self.tools = tools
        self.executor = self._build_executor()
    
    def _build_executor(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])
        agent = create_tool_calling_agent(self.llm_service.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    async def stream(self, ctx: SessionContext, user_input: str):
        # 1. RAG 检索历史相关片段
        rag_snippets = await rag_service.retrieve(
            ctx.session_id, user_input, top_k=3
        )
        
        # 2. 组装 prompt
        prompt_messages = ctx.build_prompt(user_input, rag_snippets)
        
        # 3. 流式调用
        async for event in self.executor.astream_events(
            {"input": user_input, "chat_history": prompt_messages},
            version="v2",
        ):
            if event["event"] == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield {"type": "text", "content": content}
            
            elif event["event"] == "on_tool_end":
                # 工具返回结构化数据，触发侧弹窗
                tool_name = event["name"]
                output = event["data"]["output"]
                if tool_name == "ocr_invoice":
                    yield {"type": "sidepanel", "payload": {"type": "invoice", "data": output}}
                elif tool_name == "review_contract":
                    yield {"type": "sidepanel", "payload": {"type": "contract", "data": output}}
        
        # 4. 写回消息
        await ctx.append({"role": "assistant", "content": "..."})
```

### 5.3 意图识别路由

```python
# agent/router.py
INTENT_PROMPT = """判断用户意图，返回以下之一：
- chitchat：闲聊
- policy_query：制度问答
- invoice_upload：发票上传
- contract_upload：合同上传

用户输入：{input}
附件：{file_type}

返回 JSON：{{"intent": "...", "confidence": 0.95}}
"""

async def route_intent(input: str, file_type: str | None) -> str:
    if file_type == "invoice":
        return "invoice_upload"
    if file_type == "contract":
        return "contract_upload"
    result = await llm_service.invoke(INTENT_PROMPT.format(input=input, file_type=file_type))
    return json.loads(result)["intent"]
```

### 5.4 Tools 定义

```python
# agent/tools/ocr_tool.py
from langchain.tools import tool

@tool
async def ocr_invoice(file_url: str) -> dict:
    """识别发票，返回结构化数据"""
    result = await ocr_service.recognize_invoice(file_url)
    return {
        "抬头": result.invoice_title,
        "公司": result.company,
        "税号": result.tax_id,
        "金额": result.amount,
        # ...
    }

@tool
async def review_contract(file_url: str, tenant_id: str) -> dict:
    """审查合同合规性"""
    text = await parse_contract(file_url)
    # 脱敏
    masked = mask_sensitive(text)
    # RAG 检索规则
    rules = await rag_service.retrieve_rules(tenant_id)
    # LLM 审查
    result = await llm_service.review_contract(masked, rules)
    return result

@tool
async def query_policy(question: str, tenant_id: str) -> str:
    """查询企业制度"""
    docs = await rag_service.retrieve_policy(question, tenant_id)
    return await llm_service.answer_with_context(question, docs)

@tool
async def archive_invoice(invoice_data: dict, user_id: str) -> dict:
    """归档发票"""
    return await invoice_service.archive(invoice_data, user_id)
```

---

## 6. 多轮对话与会话隔离实现

### 6.1 四层上下文策略

**第一层：完整历史（短期）**
- 最近 20 轮完整消息
- 存储：`messages` 表，按 `session_id` 查询

**第二层：摘要压缩（中期）**
- 超出 20 轮的历史，LLM 压缩成摘要
- 存储：`sessions.summary` 字段
- 触发：每 10 轮或超阈值

**第三层：结构化记忆（长期）**
- 关键实体抽取，独立存储
- 存储：`session_memory` 表
- 字段：`uploaded_invoices`、`pending_task`、`user_preference`

**第四层：RAG 检索（超长期）**
- 历史消息向量化，按需召回
- 存储：`message_embeddings` 表（pgvector）
- 触发：用户提到"上次""之前"等

### 6.2 摘要更新

```python
async def update_summary(session_id: str):
    old_summary = await get_summary(session_id)
    recent = await get_messages(session_id, limit=20)
    
    new_summary = await llm_service.invoke(f"""
    旧摘要：{old_summary}
    最近对话：{format_messages(recent)}
    
    请更新摘要，保留：上传的单据、查询的制度、待办任务、用户偏好。
    控制在 200 字以内。
    """)
    
    await save_summary(session_id, new_summary)
```

### 6.3 实体抽取

```python
async def extract_entities(session_id: str, message: str):
    entities = await llm_service.invoke(f"""
    从以下消息抽取实体，返回 JSON：
    {message}
    
    字段：uploaded_invoices, queried_policies, pending_task, user_preference
    """)
    await merge_entities(session_id, json.loads(entities))
```

### 6.4 会话隔离关键点

| 关键点 | 实现 |
|---|---|
| 请求带 session_id | 前端每次请求带，后端强制校验归属 |
| Agent 无全局状态 | 每次请求创建独立 SessionContext |
| 数据带 session_id | messages、memory、embeddings 全部带 |
| 异步任务回写 | Celery 任务带 session_id，结果写回原会话 |
| 前端状态隔离 | Zustand 中 messages 按 sessionId 分组 |
| 会话切换 | 只加载当前 session 上下文，不混入其他 |

### 6.5 异步任务回写

```python
# tasks/ocr_task.py
@celery_app.task
def ocr_task(session_id: str, filename: str, file_bytes: bytes):
    result = ocr_service.recognize(file_bytes)
    # 写回原 session
    save_message(session_id, {
        "role": "assistant",
        "content": "发票识别完成",
        "tool_calls": [{"tool": "ocr_invoice", "result": result}],
    })
    # WebSocket 通知前端
    notify_session(session_id, {"type": "ocr_done", "data": result})
```

---

## 7. OCR 方案

### 7.1 选型对比

| 方案 | 成本 | 准确率 | 适用 |
|---|---|---|---|
| 腾讯云通用印刷体 | 0.15元/次（<1万），0.06元/次（>10万），预付费0.05元/次 | 高 | MVP 首选 |
| 阿里云 OCR | 约 0.012 美元/次起 | 高 | 备选 |
| PaddleOCR 本地 | GPU 服务器成本 | 94%-96% | 数据不出域时 |

### 7.2 决策

MVP 阶段用**腾讯云 API**，月成本可控在百元内。预留 OCR 接口抽象层，未来可切本地 PaddleOCR。

### 7.3 接口抽象

```python
# services/ocr_service.py
class OCRProvider(Protocol):
    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceResult: ...

class TencentOCRProvider:
    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceResult:
        # 调用腾讯云 API
        ...

class PaddleOCRProvider:
    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceResult:
        # 本地模型
        ...

# 配置切换
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "tencent")
ocr_service = TencentOCRProvider() if OCR_PROVIDER == "tencent" else PaddleOCRProvider()
```

### 7.4 本地部署说明

- 基础 CPU 方案：4核16G，1.2 张/秒，准确率 94%
- GPU 方案：RTX 3060，8.7 张/秒，准确率 96%
- 显存占用：PP-OCRv3 全流程约 1GB

---

## 8. 合同审查方案

### 8.1 流程

```
合同解析 → 文本脱敏 → RAG 检索规则 → LLM 审查 → 结果结构化
```

### 8.2 规则维护

- 通用规则：RAG 文档「默认合规规则」，`tenant_id = NULL`
- 租户自定义：RAG 文档「租户规则」，`tenant_id = 当前租户`
- 检索：`tenant_id = 当前租户 OR tenant_id IS NULL`

### 8.3 通用规则清单

- 是否缺少盖章条款
- 付款周期是否异常
- 违约责任是否缺失
- 争议解决条款是否完整
- 合同金额是否明确
- 有效期是否明确

### 8.4 LLM 调用

```python
async def review_contract(text: str, tenant_id: str) -> dict:
    # 1. 脱敏
    masked = mask_sensitive(text)
    # 2. 检索规则
    rules = await rag_service.retrieve_rules(tenant_id)
    # 3. LLM 审查
    result = await llm_service.invoke(f"""
    你是合同合规审查专家。根据以下规则审查合同：
    
    [规则]
    {rules}
    
    [合同内容]
    {masked}
    
    返回 JSON：
    {{
      "违规项": [{{"条款": "...", "问题": "...", "严重程度": "高/中/低"}}],
      "风险等级": "高/中/低",
      "摘要": "..."
    }}
    """)
    return json.loads(result)
```

---

## 9. RAG 方案

### 9.1 技术栈

| 项 | 选型 | 理由 |
|---|---|---|
| 向量库 | pgvector | 与 PostgreSQL 一体，运维简单 |
| 备选 | Milvus | 大规模时 |
| Embedding | text-embedding-3-small / bge-m3 | 中文效果好 |
| 重排 | bge-reranker | 提升精度 |
| 切分 | 递归切分 + 语义切分 | 平衡 |
| 检索 | 向量 + 关键词混合 | 提升召回 |

### 9.2 索引流程

```python
async def index_document(doc_id: str, content: str, tenant_id: str):
    # 1. 切分
    chunks = recursive_split(content, chunk_size=500, overlap=50)
    # 2. 向量化
    embeddings = await embed(chunks)
    # 3. 存储
    for chunk, emb in zip(chunks, embeddings):
        await save_chunk(doc_id, chunk, emb, tenant_id)
```

### 9.3 检索流程

```python
async def retrieve(question: str, tenant_id: str, top_k: int = 5):
    # 1. 向量检索
    q_emb = await embed(question)
    vector_results = await vector_search(q_emb, tenant_id, top_k * 2)
    # 2. 关键词检索
    keyword_results = await keyword_search(question, tenant_id, top_k * 2)
    # 3. 合并去重
    merged = merge_results(vector_results, keyword_results)
    # 4. 重排
    reranked = await rerank(question, merged, top_k)
    return reranked
```

---

## 10. LLM 网关方案

### 10.1 技术栈

| 项 | 选型 | 理由 |
|---|---|---|
| 网关 | LiteLLM | 统一多模型，Python 原生 |
| 模型 | GPT-4o / Claude / 通义 / 文心 | 可配置 |
| 本地 | Qwen / GLM | 敏感场景 |
| 配置 | 按场景分配 | 灵活 |

### 10.2 按场景配置

```python
# services/llm_service.py
class LLMService:
    def __init__(self):
        self.configs = load_llm_configs()  # 从 DB 加载
    
    def get_llm(self, scene: str):
        config = self.configs.get(scene)
        return LiteLLM(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    
    @property
    def chitchat_llm(self):
        return self.get_llm("chitchat")
    
    @property
    def policy_llm(self):
        return self.get_llm("policy_query")
    
    @property
    def contract_llm(self):
        return self.get_llm("contract_review")
```

### 10.3 脱敏策略

```python
def mask_sensitive(text: str) -> str:
    # 税号
    text = re.sub(r'\d{15,20}', '[TAX_ID]', text)
    # 银行账号
    text = re.sub(r'\d{16,19}', '[BANK_ACCOUNT]', text)
    # 手机号
    text = re.sub(r'1[3-9]\d{9}', '[PHONE]', text)
    # 身份证
    text = re.sub(r'\d{17}[\dXx]', '[ID_CARD]', text)
    return text
```

---

## 11. 数据存储方案

### 11.1 技术栈

| 项 | 选型 | 理由 |
|---|---|---|
| 关系库 | PostgreSQL 16 | 成熟，pgvector 一体 |
| 向量 | pgvector | 与 PG 一体 |
| 缓存 | Redis 7 | 会话、队列 |
| 对象存储 | MinIO | 私有化，SSE 加密 |
| 备选 | 阿里云 OSS / 腾讯云 COS | 云部署时 |
| 加密 | AES-256 SSE | 原件加密 |
| 密钥 | 按租户独立密钥 | 为 SaaS 预留 |

### 11.2 核心表 DDL

```sql
-- 用户
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    account VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('employee', 'finance', 'admin')),
    dept VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

-- 会话
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(200),
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_user ON sessions(tenant_id, user_id, updated_at DESC);

-- 消息
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT,
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);

-- 会话记忆
CREATE TABLE session_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL,
    entity_value JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_memory_session ON session_memory(session_id);

-- 消息向量
CREATE TABLE message_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_embeddings_session ON message_embeddings(session_id);
CREATE INDEX idx_embeddings_vector ON message_embeddings USING ivfflat (embedding vector_cosine_ops);

-- 发票
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    invoice_title VARCHAR(200),
    company VARCHAR(200),
    tax_id VARCHAR(50),
    invoice_code VARCHAR(50),
    invoice_number VARCHAR(50),
    invoice_date DATE,
    amount_excl_tax NUMERIC(15,2),
    tax_amount NUMERIC(15,2),
    amount_incl_tax NUMERIC(15,2),
    invoice_type VARCHAR(20),
    seller VARCHAR(200),
    buyer VARCHAR(200),
    remark TEXT,
    file_url VARCHAR(500),
    file_hash VARCHAR(64),
    ocr_confidence JSONB,           -- 各字段识别置信度
    status VARCHAR(20) DEFAULT 'active',  -- active / withdrawn / deleted
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_invoices_tenant_user ON invoices(tenant_id, user_id, created_at DESC);
CREATE UNIQUE INDEX uk_invoices_dedup ON invoices(tenant_id, invoice_code, invoice_number)
    WHERE invoice_code IS NOT NULL AND invoice_number IS NOT NULL;
CREATE INDEX idx_invoices_status ON invoices(tenant_id, status);

-- 合同
CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    contract_name VARCHAR(300),
    contract_no VARCHAR(100),
    party_a VARCHAR(200),
    party_b VARCHAR(200),
    sign_date DATE,
    effective_start DATE,
    effective_end DATE,
    amount NUMERIC(18,2),
    key_clauses TEXT,                -- LLM 生成的关键条款摘要
    review_result JSONB,             -- 违规项列表（条款/问题/严重程度）
    risk_level VARCHAR(10),          -- high / medium / low
    file_url VARCHAR(500),
    file_hash VARCHAR(64),
    parse_status VARCHAR(20),        -- pending / success / failed
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_contracts_tenant_user ON contracts(tenant_id, user_id, created_at DESC);
CREATE INDEX idx_contracts_risk ON contracts(tenant_id, risk_level);
CREATE INDEX idx_contracts_status ON contracts(tenant_id, status);

-- 知识库文档
CREATE TABLE kb_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID,                  -- NULL 表示通用默认文档
    title VARCHAR(300) NOT NULL,
    doc_type VARCHAR(50),             -- policy / rule / template / faq
    source_file VARCHAR(500),
    content TEXT,
    chunk_count INTEGER DEFAULT 0,
    embedding_model VARCHAR(50),
    status VARCHAR(20) DEFAULT 'pending', -- pending / indexing / active / failed / disabled
    error_message TEXT,
    version INTEGER DEFAULT 1,
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_kb_tenant ON kb_documents(tenant_id, status);

-- 知识库文档切片（含向量）
CREATE TABLE kb_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    tenant_id UUID,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    token_count INTEGER,
    metadata JSONB,                  -- 章节、页码等
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_kb_chunks_doc ON kb_chunks(doc_id, chunk_index);
CREATE INDEX idx_kb_chunks_vector ON kb_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_kb_chunks_tenant ON kb_chunks(tenant_id);

-- LLM 配置
CREATE TABLE llm_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    scene VARCHAR(50) NOT NULL,      -- chitchat / policy_query / ocr_post / contract_review
    model VARCHAR(100) NOT NULL,     -- gpt-4o / claude-3.5 / qwen-plus ...
    provider VARCHAR(50),            -- openai / anthropic / aliyun / local
    api_key_encrypted TEXT,          -- AES-256 加密存储
    base_url VARCHAR(300),
    temperature NUMERIC(3,2) DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2000,
    timeout_seconds INTEGER DEFAULT 30,
    extra_params JSONB,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, scene)
);
CREATE INDEX idx_llm_configs_tenant ON llm_configs(tenant_id, enabled);

-- 审计日志
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID REFERENCES users(id),
    operation_type VARCHAR(50) NOT NULL,  -- login / invoice_archive / contract_review / file_download ...
    target_type VARCHAR(50),
    target_id UUID,
    before_value JSONB,
    after_value JSONB,
    ip VARCHAR(64),
    ua VARCHAR(500),
    result VARCHAR(20),                   -- success / failure
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_tenant_time ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX idx_audit_user ON audit_logs(tenant_id, user_id, created_at DESC);
CREATE INDEX idx_audit_target ON audit_logs(tenant_id, target_type, target_id);
-- 审计日志只追加，禁止 UPDATE/DELETE
REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC;

### 11.3 Redis 使用规划

| Key 模式 | 用途 | TTL |
|---|---|---|
| `session:{id}:lock` | 会话级互斥锁（多设备防冲突） | 60s |
| `user:{id}:active_sessions` | 用户当前活跃 session 集合 | 30 min |
| `ratelimit:{user_id}:{scene}` | 用户级限流计数 | 1 min / 1 hour |
| `llm:cache:{hash}` | LLM 响应缓存（同类问题复用） | 24 h |
| `ocr:result:{file_hash}` | OCR 结果去重（同文件不重复识别） | 7 d |
| `celery:*` | Celery 任务队列 | — |
| `socket:{session_id}` | WebSocket 连接记录 | 连接存续期 |

### 11.4 备份策略

| 数据 | 频率 | 保留 | 恢复方式 |
|---|---|---|---|
| PostgreSQL | 每日全量 + 每 6 小时增量 | 30 天 |
| MinIO 对象 | 每日增量同步 | 90 天 |
| 审计日志 | 周哈希快照 | 永久 |
| LLM 配置 | 跟随数据库备份 | 30 天 |
| RAG 向量 | 跟随数据库备份 | 30 天 |

**恢复演练**：每月一次，验证从备份恢复 + 数据完整性。

### 11.5 数据生命周期

| 数据 | 保留期 | 清理策略 |
|---|---|---|
| 会话消息 | 永久（用户可控） | 用户删除触发级联 |
| 软删发票/合同 | 30 天回收站 | 30 天后硬删 + 文件清理 |
| OCR 临时文件 | 24 h | 定时清理 |
| 审计日志 | 1 年 | 1 年后归档到冷存储 |
| 失败任务记录 | 7 天 | 自动清理 |
| WebSocket 离线消息 | 24 h | 自动清理 |

---

## 12. 安全方案

### 12.1 认证与授权

**JWT 设计**
```python
# Access Token：短期，15 min
{
  "sub": "user_id",
  "tenant_id": "tenant_id",
  "role": "employee",
  "iat": 1695000000,
  "exp": 1695000900,
  "jti": "token_uuid"
}

# Refresh Token：长期，7 天，存储到 HttpOnly Cookie
```

**密钥轮换**
- JWT 签名密钥：每 90 天轮换，双密钥并行（k1 + k2），过渡期 7 天
- 数据库加密密钥（AES-256）：按租户独立，通过 KMS 管理
- API Key：管理员可手动轮换，旧 Key 保留 24h 灰度

### 12.2 密码策略

- 长度 ≥ 10 字符，包含数字 + 字母
- bcrypt 哈希（cost = 12）
- 90 天强制过期，提前 7 天提醒
- 登录失败 5 次锁定 30 分钟
- 历史 5 次密码不能复用

### 12.3 数据加密

| 数据 | 加密方式 | 密钥 |
|---|---|---|
| 原件文件 | AES-256-GCM（MinIO SSE-KMS） | 租户级数据密钥 |
| 数据库敏感字段 | pgcrypto + 应用层 AES | 租户级数据密钥 |
| LLM API Key | AES-256 加密存储 | 主密钥（KMS） |
| 备份文件 | GPG 加密 | 独立备份密钥 |
| 传输 | TLS 1.3 | 证书（Let's Encrypt / 自签） |

### 12.4 输入校验与防护

**SQL 注入**：全 ORM 参数化，禁用原生 SQL 字符串拼接
**XSS**：前端 React 默认转义，后端返回 JSON 而非 HTML
**CSRF**：JWT 放在 Header（不放在 Cookie 可被自动发送）
**SSRF**：禁止 Agent 访问内网 URL（LLM 输出的 URL 需校验）
**文件上传**：校验 MIME + 后缀 + magic bytes，限制大小，禁止可执行文件
**AI Prompt 注入**：用户输入与工具输出严格分离，工具结果不参与 prompt 模板

### 12.5 LLM 安全

- 调用日志完整记录（prompt、response、token 消耗）
- 敏感字段先脱敏再发给 LLM（mask_sensitive 函数）
- 输出内容安全过滤（违规词、URL、内部 IP）
- 单租户 Token 用量限额（防滥用 + 成本控制）
- LLM 配置变更需管理员二次确认

### 12.6 网络与基础设施

- 所有服务在内网，仅 API / Nginx 对外
- API Gateway 限流：每用户 100 req/min，每 IP 1000 req/min
- WAF 规则（SQL/XSS/路径穿越）
- 容器镜像扫描（Trivy），CVE 高危镜像不部署
- SSH 仅允许堡垒机 + 密钥登录，禁用密码

### 12.7 密钥管理

```python
# 使用 HashiCorp Vault 或自建 KMS
class KeyManager:
    def get_tenant_key(self, tenant_id: str) -> bytes:
        # 从 Vault 读取租户数据密钥
        return vault.read(f"secret/data/{tenant_id}/data_key")
    
    def encrypt(self, plaintext: bytes, tenant_id: str) -> bytes:
        key = self.get_tenant_key(tenant_id)
        return aes_gcm_encrypt(key, plaintext)
    
    def decrypt(self, ciphertext: bytes, tenant_id: str) -> bytes:
        key = self.get_tenant_key(tenant_id)
        return aes_gcm_decrypt(key, ciphertext)
```

---

## 13. 部署方案

### 13.1 部署形态

**MVP 阶段**：Docker Compose 单机部署（私有化单企业）

**后续阶段**：Kubernetes 集群部署（多副本、SaaS 多租户）

### 13.2 服务拓扑（Docker Compose）

```
┌─────────────────────────────────────────────────┐
│  Nginx (反向代理 + TLS 终止 + SSE 缓冲配置)        │
│  端口：443                                        │
└─────────────────────────────────────────────────┘
           │
┌──────────┼──────────────────────────────────────┐
│          ▼                                       │
│  ┌─────────────┐   ┌─────────────┐              │
│  │  FastAPI    │   │  FastAPI    │  (多副本)     │
│  │  API:8000   │   │  API:8000   │              │
│  └─────────────┘   └─────────────┘              │
│           │                                       │
│  ┌────────┼────────────────────────────────┐    │
│  │        ▼                                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌────────┐  │    │
│  │  │ Celery   │  │ Celery   │  │ Beat   │  │    │
│  │  │ Worker   │  │ Worker   │  │        │  │    │
│  │  └──────────┘  └──────────┘  └────────┘  │    │
│  └────────────────────────────────────────┘    │
│           │                                       │
│  ┌────────┼────────────────────────────────┐    │
│  │  PostgreSQL + pgvector                   │    │
│  │  Redis                                    │    │
│  │  MinIO                                    │    │
│  └────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### 13.3 Nginx 配置要点

```nginx
# SSE 流式不缓冲
location /api/chat/stream {
    proxy_pass http://backend;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding on;
}

# WebSocket
location /api/ws {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
}

# 大文件上传
client_max_body_size 50m;
```

### 13.4 资源配置（最小生产配置）

| 服务 | CPU | 内存 | 磁盘 | 数量 |
|---|---|---|---|---|
| Nginx | 1 | 512MB | — | 1 |
| FastAPI | 2 | 4GB | — | 2（可扩） |
| Celery Worker | 2 | 4GB | — | 2（可扩） |
| PostgreSQL | 4 | 8GB | 100GB SSD | 1 |
| Redis | 1 | 1GB | — | 1 |
| MinIO | 1 | 1GB | 500GB | 1 |
| Prometheus + Grafana | 1 | 2GB | 50GB | 1 |

**总建议**：8 核 16GB 100GB SSD 起，可支撑 200 并发。

### 13.5 灰度与回滚

- **蓝绿部署**：新旧版本并存，通过 Nginx upstream 切换
- **金丝雀**：10% 流量切到新版本，观察 30 分钟无异常后全量
- **回滚**：镜像保留 3 个版本，数据库迁移可逆向（Alembic downgrade）
- **熔断**：新版本错误率 > 5% 自动回滚

### 13.6 健康检查

```python
@router.get("/health")
async def health():
    return {
        "status": "ok",
        "db": await check_db(),
        "redis": await check_redis(),
        "minio": await check_minio(),
        "llm": await check_llm_connectivity(),
    }
```

K8s/Compose liveness/readiness 探针使用此端点。

### 13.7 数据库迁移

```bash
# 生成迁移
alembic revision --autogenerate -m "add contracts table"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

迁移规范：禁止破坏性变更（drop column 需先 add 新 column + 双写 + 数据迁移 + drop）。

---

## 14. 多租户演进设计

### 14.1 当前架构对多租户的支持

- 所有业务表带 `tenant_id NOT NULL`
- 所有查询强制 `WHERE tenant_id = ?`
- 租户隔离在 ORM 层 + 数据库层双重防护
- 文件存储按租户分桶（MinIO bucket per tenant）

### 14.2 演进路径

**阶段 1（私有化单租户）→ 阶段 2（SaaS 多租户）需要补齐的能力**

| 能力 | 当前 | 演进方案 |
|---|---|---|
| 租户路由 | 配置中固定 | 子域名 `tenant.app.com` 或 Header `X-Tenant-ID` |
| 租户管理 | 无 | 超级管理员后台：创建租户、配置独立域名、计费 |
| 资源配额 | 无 | 每租户：用户数、存储、Token 配额 |
| 计费 | 无 | 用量打点（OCR/次数、LLM Token、存储 GB）+ 计费引擎 |
| 数据迁移 | 无 | 私有化→SaaS：ETL 工具，支持结构化导出 |
| 跨租户查询 | 不允许 | 仅超级管理员 + 审计留痕 |
| 独立密钥 | 预留 | 每租户独立 KMS 数据密钥 |
| 域名证书 | 共享 | 每租户独立证书（自动签发 Let's Encrypt） |

### 14.3 租户路由实现

```python
# 通过子域名识别租户
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0]
    
    if subdomain and subdomain != "www":
        request.state.tenant_id = resolve_tenant_by_domain(subdomain)
    else:
        # Header 模式（开发 / API 调用）
        request.state.tenant_id = request.headers.get("X-Tenant-ID")
    
    response = await call_next(request)
    return response
```

### 14.4 数据隔离策略

**共享数据库 + tenant_id 过滤（推荐）**
- 成本低、运维简单、统计方便
- 风险：SQL 注入绕过 tenant_id
- 缓解：ORM 强制注入 + 数据库视图 + 定期审计

**独立 schema（中等隔离）**
- 每租户一个 schema，跨 schema 查询需要权限
- 适合中型 SaaS（< 1000 租户）

**独立数据库（强隔离）**
- 每租户独立 PG 实例
- 适合大型客户、合规要求高

**MVP 选型**：共享数据库 + tenant_id，业务代码不感知。

### 14.5 资源配额

```python
class TenantQuota:
    max_users: int = 100
    max_storage_gb: int = 100
    monthly_llm_tokens: int = 1_000_000
    monthly_ocr_calls: int = 10_000
    
    def check(self, usage: dict) -> bool:
        # 调用前校验，超额返回 429
        ...
```

### 14.6 计费打点

```python
# 用量事件统一打点
emit_usage_event(
    tenant_id="t1",
    event_type="ocr_call",
    quantity=1,
    metadata={"provider": "tencent", "doc_type": "invoice"}
)
```

汇总到 `usage_events` 表，计费引擎按周期聚合出账单。

---

## 15. 性能与可观测性

### 15.1 性能指标体系

**应用层指标（Prometheus）**
- `http_requests_total{method, path, status}`
- `http_request_duration_seconds{method, path}`（Histogram）
- `agent_invocations_total{scene, result}`
- `agent_invocation_duration_seconds{scene}`（Histogram）
- `llm_tokens_total{tenant, scene, model}`
- `ocr_calls_total{provider, result}`
- `active_sessions_count`
- `rag_retrieval_duration_seconds`

**业务指标**
- 每日归档发票数
- 每日归档合同数
- 合同高风险数量
- 用户活跃数（DAU / MAU）
- 平均会话长度

### 15.2 关键 SLI/SLO

| 指标 | SLI | SLO 目标 |
|---|---|---|
| API 可用性 | 成功请求 / 总请求 | ≥ 99.5% |
| OCR P95 延迟 | 识别接口响应时间 | ≤ 5s |
| 合同审查 P95 | 审查完成时间 | ≤ 15s |
| RAG 问答 P95 | 问答响应时间 | ≤ 3s |
| 会话切换 P95 | 切换加载时间 | ≤ 500ms |
| 首屏 P95 | 页面加载时间 | ≤ 2s |
| LLM 调用成功率 | 成功 / 调用 | ≥ 99% |

### 15.3 日志规范

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "invoice.archived",
    tenant_id=tenant_id,
    user_id=user_id,
    invoice_id=invoice_id,
    amount=amount,
    duration_ms=duration,
    request_id=request_id,
)
```

**日志字段规范**
- 必填：`timestamp` / `level` / `service` / `request_id` / `tenant_id` / `user_id`
- 可选：`trace_id` / `span_id`（OpenTelemetry）
- 格式：JSON（Loki / ELK 友好）

### 15.4 链路追踪

- OpenTelemetry SDK（FastAPI / SQLAlchemy / LangChain）
- Trace 上报到 Langfuse（Agent 步骤）+ Tempo/Jaeger（全链路）
- 关键 span：API → Agent → Tool → LLM → DB

### 15.5 告警规则

| 告警 | 触发条件 | 级别 |
|---|---|---|
| API 错误率 | 5xx 占比 > 1%（5 分钟） | P2 |
| OCR 错误率 | OCR 失败 > 10%（10 分钟） | P3 |
| LLM 调用超时 | 超时率 > 5%（5 分钟） | P2 |
| 数据库连接耗尽 | 活跃连接 > 80% | P1 |
| 磁盘空间 | 使用 > 80% | P2 |
| 内存使用 | > 85% | P2 |
| 合同高风险 | 单日新增 ≥ 5 份 | P3 |
| 异常登录 | 同 IP 失败 ≥ 20 次 | P2 |

### 15.6 监控大盘

- **业务大盘**：DAU、归档趋势、合同风险分布、LLM 用量
- **应用大盘**：API QPS、P95 延迟、错误率、慢 SQL
- **基础设施大盘**：CPU/内存/磁盘、网络、容器状态

### 15.7 限流策略

```python
# 用户级限流
@limiter.limit("100/minute", key_func=lambda: g.user.id)
async def chat_stream(): ...

# 租户级限流
@limiter.limit("10000/hour", scope="tenant")
async def ocr_endpoint(): ...

# 全局限流（防恶意）
@limiter.limit("1000/minute", scope="global", key_func=get_remote_address)
async def public_endpoint(): ...
```

---

## 16. 成本估算

### 16.1 单企业（月活 200 人）月度成本估算

**第三方 API 费用**

| 项目 | 单价 | 月用量 | 月成本 |
|---|---|---|---|
| 腾讯云 OCR | 0.15 元/次 | 5000 次 | 750 元 |
| GPT-4o（输入） | $2.5/M tokens | 5M tokens | $12.5 |
| GPT-4o（输出） | $10/M tokens | 2M tokens | $20 |
| Embedding | $0.02/M tokens | 3M tokens | $0.06 |
| 总计 LLM | | | ~$32.5 |

**基础设施**

| 项目 | 配置 | 月成本（云） |
|---|---|---|
| 应用服务器 | 4 核 8GB × 2 | ¥600 |
| 数据库 | 4 核 8GB SSD 100GB | ¥400 |
| Redis | 1GB | ¥50 |
| 对象存储 | 500GB | ¥100 |
| 带宽 | 5TB | ¥200 |
| 总计 | | **¥1350** |

**总计：约 ¥2200 / 月（含 LLM 约 ¥2400）**

### 16.2 成本优化策略

| 策略 | 节省 | 实现 |
|---|---|---|
| LLM 响应缓存（同类问题） | 30-50% | Redis 缓存 prompt hash → response |
| OCR 缓存（同文件不重复） | 10-20% | 文件 hash 去重 |
| 选择更小模型 | 50% | 闲聊用 GPT-4o-mini，识别用 gpt-4o |
| 本地模型替代 | 60%+ | 闲聊/分类用本地 GLM-4 / Qwen2.5 |
| 向量库压缩 | 20% | pgvector 量化 |
| 按租户配额 | 防止滥用 | 配额校验 |

### 16.3 扩容阈值

| 指标 | 阈值 | 动作 |
|---|---|---|
| API CPU > 70% 持续 10 分钟 | 加副本 |
| 数据库连接 > 80% | 优化 + 分库 |
| LLM 月用量 > 80% 配额 | 通知管理员 |
| 对象存储 > 80% | 清理 + 扩容 |
| 慢查询 P95 > 3s | 加索引 / 优化 |

---

## 17. 技术风险与应对

| 风险 | 等级 | 影响 | 应对措施 |
|---|---|---|---|
| LLM 幻觉（错误识别） | 高 | 数据污染 | 强制人工确认、置信度低字段标黄、定期抽样审计 |
| LLM 服务中断 | 高 | 业务不可用 | 多模型配置（4o + Claude + 国产），降级到本地小模型 |
| OCR 准确率不足 | 中 | 用户反复修改 | 多 OCR 引擎投票、置信度提示、字段级反馈 |
| 上下文窗口溢出 | 中 | 会话丢失 | 四层策略（短/中/长/RAG）已设计 |
| Embedding 模型升级 | 中 | 向量库失效 | 灰度切换 + 旧向量保留 30 天兼容 |
| RAG 召回不准 | 中 | 问答答非所问 | 重排序 + 混合检索 + 用户反馈闭环 |
| 第三方 API 限流 | 中 | 任务积压 | 队列 + 重试 + 备用 provider |
| 数据库性能瓶颈 | 中 | 慢响应 | 索引 + 读写分离 + 分库 |
| 敏感数据泄露 | 高 | 合规事故 | 脱敏 + 加密 + 行级权限 + 审计 |
| AI Prompt 注入 | 高 | 越权操作 | 用户输入与工具输出严格分离 + 输入扫描 |
| 大文件上传 OOM | 中 | 服务崩溃 | 流式分片上传 + 大小限制 |
| WebSocket 大量并发 | 中 | 连接耗尽 | 单机 1w 连接限制 + 多实例 + 负载均衡 |
| 审计日志膨胀 | 低 | 性能下降 | 月度归档 + 冷热分层 |
| 私部署环境差异 | 中 | 兼容性问题 | Docker 标准化 + 严格 CI 测试矩阵 |

### 17.1 风险缓解机制

**LLM 关键风险**
- 4 个模型互备 + 人工兜底
- 所有 Agent 决策保留中间产物（langfuse trace）
- 关键操作（归档）必须二次确认

**合规风险**
- 等保三级方案预留（密码复杂度、审计、操作鉴权）
- 数据本地化（私有化部署）
- 第三方 API 调用前必脱敏

**业务风险**
- 上线前用 100 份真实合同 / 发票测试集验证
- 灰度发布（财务部门先试）
- 7×24 故障响应

---

## 18. 测试方案

### 18.1 测试金字塔

```
                /\
               /  \  E2E（Playwright，5%）
              /────\
             /      \  集成测试（pytest，25%）
            /────────\
           /          \ 单元测试（vitest + pytest，70%）
          /────────────\
```

### 18.2 后端测试（pytest）

**单元测试**
```python
# services/test_ocr_service.py
def test_invoice_field_extraction():
    raw = load_fixture("invoice_sample.jpg")
    result = ocr_service.recognize(raw)
    assert result.invoice_code == "011002100311"
    assert result.amount_incl_tax == Decimal("1130.00")

# tools/test_rag_tool.py
def test_policy_retrieval():
    docs = rag_service.retrieve_policy("差旅补贴", tenant_id="t1")
    assert len(docs) > 0
    assert "上海" in docs[0].content
```

**集成测试**
- API 端到端：登录 → 上传 → OCR → 归档
- 数据库迁移：Alembic 升级 + 回滚
- Redis 缓存：序列化 / 反序列化
- Celery 任务：异步 OCR / 合同审查

**覆盖率目标**：核心服务 ≥ 80%，Agent / Tools ≥ 60%

### 18.3 前端测试（vitest + Playwright）

**单元测试**
- 组件渲染（React Testing Library）
- 状态管理（Zustand store）
- Hooks（useSSE / useSession）
- 表单校验（Zod schema）

**E2E（Playwright）**
```typescript
test('employee uploads invoice', async ({ page }) => {
  await page.goto('/login');
  await page.fill('[name=account]', 'employee01');
  await page.fill('[name=password]', 'password');
  await page.click('button[type=submit]');
  
  await page.click('[data-testid=new-session]');
  await page.setInputFiles('[data-testid=upload]', 'invoice.jpg');
  await expect(page.locator('[data-testid=sidepanel]')).toBeVisible();
  await page.click('[data-testid=confirm-archive]');
  
  await expect(page.locator('text=已归档')).toBeVisible();
});
```

### 18.4 合同审查测试集

构建 100 份标注合同（覆盖常见违规项）：
- 缺失盖章条款
- 付款周期异常
- 违约责任缺失
- 争议解决条款不完整
- 合同金额不明确
- 有效期不明确

**评估指标**：召回率 ≥ 90%，误报率 ≤ 15%

### 18.5 性能测试（k6 / Locust）

```javascript
// k6 脚本
import http from 'k6/http';

export const options = {
  stages: [
    { duration: '2m', target: 100 },  // 100 用户
    { duration: '5m', target: 200 },  // 200 用户
    { duration: '2m', target: 0 },
  ],
};

export default function () {
  http.post('/api/chat/stream', {...});
}
```

**指标**：200 并发用户下，P95 延迟 ≤ SLO 目标。

### 18.6 LLM 测试

- **回归测试**：100 条典型问答，评估输出稳定性
- **A/B 测试**：新旧 prompt 对比
- **Token 消耗基线**：异常消耗告警
- **安全测试**：Prompt 注入用例库

### 18.7 测试数据管理

- 固定 fixture（`tests/fixtures/`）
- 数据库隔离：每个测试用独立 schema / 容器
- 测试后清理（truncate tables）
- 敏感数据脱敏

---

## 19. CI/CD 与工程化

### 19.1 分支策略

```
main (生产)
  ↑
  PR + Code Review
  ↑
develop (集成)
  ↑
feature/* → develop
hotfix/* → main + develop
release/* → main + develop
```

### 19.2 CI 流水线（GitHub Actions）

```yaml
name: CI

on: [push, pull_request]

jobs:
  lint:
    steps:
      - run: ruff check backend/
      - run: eslint src/ --max-warnings 0
  
  test-backend:
    services:
      postgres:
        image: pgvector/pgvector:pg16
      redis:
        image: redis:7
    steps:
      - run: pytest --cov=app --cov-report=xml --cov-fail-under=80
  
  test-frontend:
    steps:
      - run: vitest run --coverage
      - run: playwright test
  
  build:
    steps:
      - name: Build backend image
        run: docker build -t app:${{ github.sha }} backend/
      - name: Build frontend image
        run: docker build -t web:${{ github.sha }} frontend/
  
  security-scan:
    steps:
      - run: trivy image app:${{ github.sha }}
      - run: bandit -r backend/
```

### 19.3 CD 流水线

**自动部署流程**
1. PR 合入 main → 触发构建
2. 镜像推送至私有 Registry
3. 测试环境自动部署
4. 自动化集成测试 + 烟雾测试
5. 手动批准 → 生产环境金丝雀 10%
6. 监控 30 分钟无异常 → 全量
7. 失败自动回滚

### 19.4 数据库迁移流程

```bash
# 开发
alembic revision --autogenerate -m "add audit_logs"

# CI 中自动 dry-run upgrade head
alembic upgrade head --sql > migration.sql  # 生成 SQL 审核

# 生产部署
alembic upgrade head  # 部署前自动备份
```

### 19.5 制品管理

| 制品 | 存储 | 版本策略 |
|---|---|---|
| Docker 镜像 | Harbor / GHCR | git SHA + latest |
| 前端构建产物 | Nginx 静态目录 | git SHA |
| Python wheel | 私有 PyPI | semver |
| 数据库迁移 SQL | 与代码同仓库 | 与代码版本同步 |

### 19.6 代码规范

- **Python**：black + ruff + mypy（strict）
- **TypeScript**：ESLint + Prettier + tsc --noEmit
- **Git Commit**：Conventional Commits（feat/fix/docs/refactor/...）
- **PR 模板**：变更说明、测试覆盖、影响范围、截图

### 19.7 文档同步

- OpenAPI 文档自动生成（FastAPI）
- TypeScript 类型从 OpenAPI 自动生成
- 数据库 schema 自动生成 ER 图
- README + 部署手册 + 运维手册

### 19.8 环境分层

| 环境 | 用途 | 数据 |
|---|---|---|
| dev | 开发自测 | 假数据 |
| staging | 集成测试 | 脱敏生产数据 |
| pre-prod | 上线前验证 | 生产快照 |
| prod | 生产 | 真实数据 |

**严禁**：prod 数据进入非 prod 环境；dev 数据进入 prod。

---

## 20. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-09-20 | 初版，覆盖技术选型、架构、前后端方案、Agent、RAG、安全、部署、测试、CI/CD |

---