# 企业 AI Agent 财务智能与单据处理平台

## 产品文档（PRD）

**版本**：V1.0
**阶段**：私有化单企业部署，预留 SaaS 多租户升级
**日期**：2026-09-20

---

## 目录

1. 产品背景
2. 功能设计理念
3. 角色与权限
4. 核心用户旅程
5. 功能模块详细设计
6. 多轮对话与会话隔离设计
7. 数据模型
8. 非功能需求
9. MVP 路线图

---

## 1. 产品背景

### 1.1 行业痛点

企业财务单据处理长期存在以下问题：

**员工侧**：
- 报销流程繁琐，手工填写发票信息易出错
- 不清楚公司报销制度、差旅补贴标准，反复询问财务
- 发票丢失、重复提交、抬头错误导致退单

**财务侧**：
- 人工录入发票信息，效率低、易出错
- 合同审查依赖人工经验，违规条款难以系统性发现
- 单据归档分散，检索困难，审计追溯成本高

**管理侧**：
- 财务制度更新后，员工知晓率低
- 缺乏统一的数据看板，无法掌握报销与合同全貌
- 合规风险前置能力弱，往往事后才发现问题

### 1.2 产品机会

大语言模型与 OCR 技术的成熟，使得「对话即操作」成为可能。员工不需要学习复杂的财务系统，只需在聊天窗口上传发票、提问制度，AI Agent 自动完成识别、结构化、审查、归档。

### 1.3 产品定位

**一句话定位**：以对话为入口的企业财务 AI Agent 平台，完成发票/合同的智能识别、结构化归档、合规审查与制度问答。

**核心价值主张**：
- 对员工：上传即识别，对话即查询，零学习成本
- 对财务：统一归档、可追溯、合规风险前置
- 对管理：知识库可维护、LLM 可配置、数据可洞察

---

## 2. 功能设计理念

### 2.1 设计原则

**原则一：对话优先，而非表单优先**
传统财务系统要求用户填表单，本产品以 Chat 为主界面，用户用自然语言表达意图，Agent 自动路由到对应能力。上传发票、查制度、闲聊，都在同一个输入框完成。

**原则二：AI 做识别，人做确认**
AI 识别结果不直接入库，而是通过侧弹窗展示，用户可编辑、确认后再归档。既保证效率，又保留人工兜底，避免 AI 错误直接污染数据。

**原则三：敏感数据边界清晰**
发票、合同属于企业敏感数据。OCR 可走云服务，但合同合规审查的 LLM 调用需脱敏处理。原件加密存储，权限行级隔离。

**原则四：为 SaaS 预留，但不为 SaaS 过度设计**
当前私有化单企业部署，但所有数据表加 `tenant_id`，权限查询强制带租户过滤。未来升 SaaS 时，只需注入租户上下文，不改业务逻辑。

**原则五：规则即知识，可演进**
合同合规规则以 RAG 文档形式维护，通用规则是默认文档，租户自定义规则是额外文档。升级多租户时，只需按 `tenant_id` 过滤，不重写审查逻辑。

**原则六：会话隔离，上下文不串台**
每个会话是独立的上下文单元。多轮对话通过「完整历史 + 摘要 + 结构化记忆 + RAG」四层策略管理上下文，切换会话时严格隔离，互不污染。

### 2.2 核心设计取舍

| 决策点 | 选择 | 理由 |
|---|---|---|
| 交互入口 | Chat 优先 | 降低学习成本 |
| AI 结果处理 | 人工确认后入库 | 避免错误数据污染 |
| OCR 部署 | 云 API 优先 | 成本低，MVP 快 |
| 合同审查 LLM | 脱敏后外部 API | 平衡效果与合规 |
| 原件存储 | 服务端加密 | 安全合规 |
| 权限粒度 | 行级（tenant + user） | 为 SaaS 预留 |
| 规则维护 | RAG 文档 | 可演进，不写死 |

---

## 3. 角色与权限

| 角色 | 权限范围 |
|---|---|
| 普通员工 | 仅查看自己的发票/合同；使用 Chat、上传、归档 |
| 财务人员 | 查看全公司发票/合同；审核、导出、下载原件 |
| 管理员 | 全部权限 + 用户管理、RAG 知识库、LLM 设置 |

**权限校验规则**：
- 所有查询强制带 `tenant_id`
- 员工角色额外强制 `user_id = 当前用户`
- 财务/管理员可跨用户查询，但仍在同一租户内

---

## 4. 核心用户旅程

### 旅程一：员工报销发票

1. 登录 → 进入 Chat 界面
2. 上传发票图片/PDF
3. Agent 识别 → 侧弹窗展示结构化字段
4. 用户核对/编辑 → 点击「确定归档」
5. 发票入库，原件加密存储

### 旅程二：员工查询差旅补贴

1. 在 Chat 输入「出差去上海，住宿补贴多少？」
2. Agent 识别为制度问答 → RAG 检索 → LLM 生成回答
3. 回答附带制度来源引用

### 旅程三：财务审查合同

1. 上传合同 PDF
2. Agent 解析 → 合规审查 → 侧弹窗展示结构化字段 + 风险项
3. 财务确认 → 归档，风险等级记录

### 旅程四：管理员维护知识库

1. 后台入口 → 新窗口打开
2. RAG 知识库 → 上传制度文档 → 自动切分/向量化
3. 检索测试 → 验证问答效果

### 旅程五：多会话切换

1. 用户在与会话 A 讨论发票归档
2. 切换到会话 B 查询差旅制度
3. 会话 B 独立上下文，不携带 A 的信息
4. 切回会话 A，A 的上下文完整恢复

---

## 5. 功能模块详细设计

### 5.1 登录模块

**功能**：
- 账号密码登录
- 预留企业 SSO 接口（OAuth2/SAML）
- 登录态管理（JWT + Refresh Token）
- 登录失败次数限制

**页面**：
- 登录页：Logo、账号、密码、登录按钮
- 错误提示：账号或密码错误、账号被锁定

### 5.2 Chat 主界面

**布局**：
- 左侧：会话列表（支持多会话、新建、重命名、删除）
- 中间：消息流（用户消息 + Agent 回复）
- 底部：输入框 + 上传按钮
- 右侧：侧弹窗（识别结果展示时出现）

**能力路由**：
Agent 通过意图识别将用户输入路由到：
- 闲聊 → 通用 LLM
- 制度问答 → RAG 检索 + LLM
- 发票上传 → OCR + 结构化
- 合同上传 → 解析 + 合规审查

**消息类型**：
- 纯文本消息
- 文件消息（发票/合同）
- 结构化卡片消息（识别结果摘要）
- 侧弹窗触发消息

**流式输出**：
Agent 回复采用流式（SSE/WebSocket），提升体验。

### 5.3 发票识别与归档

**流程**：
```
上传 → OCR识别 → 结构化提取 → 侧弹窗展示 → 用户编辑 → 确定归档 → 入库+原件加密存储
```

**侧弹窗字段**：

| 字段 | 说明 | 可编辑 |
|---|---|---|
| 发票抬头 | 购买方名称 | 是 |
| 公司名称 | 开票公司 | 是 |
| 税号 | 纳税人识别号 | 是 |
| 发票代码 | 发票代码 | 是 |
| 发票号码 | 发票号码 | 是 |
| 开票日期 | 日期 | 是 |
| 金额（不含税） | 数值 | 是 |
| 税额 | 数值 | 是 |
| 金额（含税） | 数值 | 是 |
| 发票类型 | 专票/普票/电子 | 是 |
| 销售方 | 销售方名称 | 是 |
| 购买方 | 购买方名称 | 是 |
| 备注 | 文本 | 是 |

**操作按钮**：
- 确定归档：写入数据库，原件加密存储
- 重新识别：重新调用 OCR
- 取消：关闭弹窗，不归档

**去重校验**：
归档前校验发票代码+号码是否已存在，避免重复报销。

### 5.4 合同识别与合规审查

**流程**：
```
上传 → 解析 → 结构化 → 合规审查 → 侧弹窗展示(含风险) → 用户确认 → 归档
```

**侧弹窗字段**：

| 字段 | 说明 |
|---|---|
| 合同名称 | 文本 |
| 合同编号 | 文本 |
| 甲方 | 文本 |
| 乙方 | 文本 |
| 签订日期 | 日期 |
| 有效期 | 起止日期 |
| 合同金额 | 数值 |
| 关键条款摘要 | LLM 生成 |
| 合规审查结果 | 违规项列表 |
| 风险等级 | 高/中/低 |

**合规审查规则（通用）**：
- 是否缺少盖章条款
- 付款周期是否异常
- 违约责任是否缺失
- 争议解决条款是否完整
- 合同金额是否明确
- 有效期是否明确

**风险展示**：
违规项高亮，附审查说明。风险等级按违规项数量与严重程度计算。

### 5.5 RAG 制度问答

**流程**：
```
提问 → 意图识别 → RAG检索 → LLM生成 → 回答(附来源)
```

**知识库内容**：
- 报销制度
- 差旅补贴标准
- 合同模板
- 合规规则
- 其他企业制度

**检索策略**：
- 向量检索 + 关键词检索混合
- 重排序（Rerank）提升精度
- 返回 Top-K 片段注入 LLM

**回答格式**：
- 直接回答
- 来源引用（文档名 + 片段）
- 如无匹配，明确告知未找到相关制度

### 5.6 后台管理端

**入口**：Chat 界面右上角「后台入口」→ 浏览器新窗口打开

**菜单结构**：

#### 5.6.1 首页
- 数据概览：今日归档数、发票总额、合同数、风险合同数
- 趋势图：近7天/30天归档趋势
- 最近操作：最近归档记录

#### 5.6.2 发票归档
- 列表：抬头、公司、金额、日期、状态、上传人
- 筛选：日期范围、金额范围、上传人、发票类型
- 详情：结构化字段 + 原件预览
- 操作：查看、下载原件、导出 Excel

#### 5.6.3 合同归档
- 列表：合同名、甲乙方、金额、风险等级、上传人
- 筛选：日期、风险等级、上传人
- 详情：结构化字段 + 合规审查报告 + 原件预览
- 操作：查看、下载原件、导出

#### 5.6.4 RAG 知识库
- 文档列表：标题、类型、状态、上传时间
- 上传文档：支持 PDF/Word/TXT
- 切分/向量化状态展示
- 检索测试：输入问题，查看召回片段
- 操作：启停、删除、重新向量化

#### 5.6.5 用户管理
- 用户列表：姓名、账号、角色、部门、状态
- 增删改查
- 角色分配：员工/财务/管理员
- 密码重置

#### 5.6.6 LLM 设置
- 模型选择：GPT/Claude/通义/文心/本地
- API Key、Base URL、温度、Max Tokens、System Prompt
- 按场景配置：
  - 闲聊模型
  - 制度问答模型
  - 单据识别模型
  - 合同审查模型
- 连通性测试

---

## 6. 多轮对话与会话隔离设计

### 6.1 核心问题

LLM 本身无状态，每次调用都是独立的。所谓"记住之前几轮"，靠的是每次请求时把历史上下文一起传入。但上下文窗口有限，且多会话切换时容易串台。

### 6.2 上下文管理四层策略

**第一层：完整历史（短期）**
最近 N 轮（建议 10-20 轮）完整保留，包括用户消息、Agent 回复、工具调用结果。精度最高。

**第二层：摘要压缩（中期）**
超出 N 轮的历史，用 LLM 压缩成摘要，滚动更新。例如：

```
[历史摘要]
用户上传了 3 张发票，已归档。
用户询问了上海出差住宿补贴，答：500元/晚。
用户上传了一份采购合同，风险等级：中。
```

**第三层：结构化记忆（长期）**
把关键实体抽取出来单独存储，不依赖 LLM 记忆。例如：

```json
{
  "session_id": "s456",
  "entities": {
    "uploaded_invoices": ["inv_001", "inv_002"],
    "current_task": "发票归档",
    "pending_confirmation": "inv_003"
  }
}
```

**第四层：RAG 检索（超长期）**
历史消息全部向量化存入向量库。当用户提到"上次那张发票"，Agent 用 RAG 检索历史消息，召回相关片段注入 prompt。

### 6.3 上下文组装顺序

每次调用 LLM 时，prompt 按以下顺序组装：

```
[System Prompt]
  - 角色定义
  - 当前会话摘要
  - 结构化记忆（实体、状态）
  - 相关历史片段（RAG 召回）
  - 工具定义

[Recent Messages]
  - 最近 N 轮完整对话

[Current User Input]
  - 当前用户输入
```

### 6.4 会话隔离原则

**原则一：每个会话是独立上下文单元**
切换会话时，Agent 只加载当前会话的上下文，绝不混入其他会话。

**原则二：所有数据带 session_id**
messages、session_memory、embeddings 全部带 session_id，查询强制过滤。

**原则三：Agent 不持有全局状态**
Agent 编排层不能有全局 memory 变量。每次请求创建独立 SessionContext，请求结束销毁。

**原则四：异步任务回写原 session**
OCR、合同审查是异步任务，完成后必须带 session_id 写回对应会话，不能写全局队列。

### 6.5 会话切换流程

```
用户点击会话 B
  → 前端请求 /sessions/B/messages
  → 后端校验 session B 属于当前用户
  → 加载 B 的消息列表 + 摘要 + 结构化记忆
  → 前端渲染 B 的对话
  → 后续 Agent 调用只带 B 的上下文
```

### 6.6 上下文对象设计

```python
class SessionContext:
    def __init__(self, session_id, user_id, tenant_id):
        self.session_id = session_id
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.recent_messages = []      # 最近N轮
        self.summary = ""               # 中期摘要
        self.entities = {}              # 结构化记忆
        self.pending_task = None        # 待确认任务

    def load(self):
        # 从DB加载当前session的上下文
        ...

    def append(self, message):
        # 追加消息并更新摘要/实体
        ...
```

### 6.7 摘要更新策略

每 N 轮（如 10 轮）或上下文超阈值时，触发摘要更新：

```python
def update_summary(session_id):
    old_summary = get_summary(session_id)
    recent = get_messages(session_id, limit=20)
    
    new_summary = llm.invoke(f"""
    旧摘要：{old_summary}
    最近对话：{recent}
    
    请更新摘要，保留关键信息：上传的单据、查询的制度、待办任务、用户偏好。
    """)
    
    save_summary(session_id, new_summary)
```

### 6.8 实体抽取策略

每轮对话后，用轻量 LLM 或规则抽取实体：

```python
def extract_entities(session_id, message):
    entities = llm.invoke(f"""
    从以下消息抽取实体，返回JSON：
    {message}
    
    字段：uploaded_invoices, queried_policies, pending_task, user_preference
    """)
    
    merge_entities(session_id, entities)
```

### 6.9 边界情况处理

| 场景 | 处理 |
|---|---|
| 用户切换会话后回来 | 加载该 session 的完整上下文，不受其他会话影响 |
| 异步任务完成时用户已切走 | 结果写回原 session，前端通过 WebSocket 通知 |
| 会话过长超上下文 | 摘要 + 实体 + RAG 三层兜底 |
| 用户删除会话 | 级联删除 messages、memory、embeddings |
| 多设备同时登录 | 同一 session 加锁，或提示"会话在其他设备活跃" |
| 用户提到"上次那张发票" | RAG 检索该 session 历史消息，召回相关片段 |
| 用户新建会话 | 创建新 session_id，空上下文，不复用旧会话 |
| 会话重命名 | 仅更新 title，不影响上下文 |

---

## 7. 数据模型

### 7.1 核心表

**users**
- id, tenant_id, name, account, password_hash, role, dept, status, created_at

**sessions**
- id, tenant_id, user_id, title, summary, created_at, updated_at

**messages**
- id, tenant_id, session_id, role, content, tool_calls, created_at

**session_memory**
- id, session_id, entity_type, entity_value, updated_at

**message_embeddings**
- id, session_id, message_id, embedding, created_at

**invoices**
- id, tenant_id, user_id, 抬头, 公司, 税号, 发票代码, 发票号码, 开票日期, 金额不含税, 税额, 金额含税, 发票类型, 销售方, 购买方, 备注, 原件url, 原件hash, 状态, created_at

**contracts**
- id, tenant_id, user_id, 合同名称, 合同编号, 甲方, 乙方, 签订日期, 有效期起, 有效期止, 合同金额, 关键条款摘要, 合规审查结果, 风险等级, 原件url, 原件hash, 状态, created_at

**kb_documents**
- id, tenant_id, 标题, 类型, 内容, 向量id, 状态, created_at

**llm_configs**
- id, tenant_id, 场景, 模型, api_key, base_url, 参数, created_at

**audit_logs**
- id, tenant_id, user_id, 操作类型, 目标id, 详情, created_at

### 7.2 索引建议

- sessions: (tenant_id, user_id, updated_at)
- messages: (session_id, created_at)
- invoices: (tenant_id, user_id, created_at), (tenant_id, 发票代码, 发票号码)
- contracts: (tenant_id, user_id, created_at), (tenant_id, 风险等级)

---

## 8. 非功能需求

**性能**：
- OCR 识别 < 5s
- 合同审查 < 15s
- RAG 问答 < 3s
- 页面加载 < 2s
- 会话切换 < 500ms

**安全**：
- 原件 AES-256 加密存储
- 传输 HTTPS
- 行级权限隔离
- 操作审计日志
- 合同审查前敏感字段脱敏

**可用性**：
- 99.5% 可用性
- 数据每日备份

**扩展性**：
- 所有表含 tenant_id
- 规则以 RAG 文档维护
- LLM 可配置多模型
- Agent 编排无全局状态，支持水平扩展

---

## 9. MVP 路线图

**Phase 1（4–6 周）**
- 登录 + Chat 主界面
- 会话列表 + 会话隔离
- 发票上传 → OCR → 侧弹窗 → 归档
- 后台：发票归档、用户管理

**Phase 2（4 周）**
- 合同上传 + 合规审查
- 后台：合同归档、RAG 知识库
- 摘要 + 结构化记忆

**Phase 3（3 周）**
- 制度问答 RAG 接入
- LLM 设置、首页看板
- 权限细化、审计日志
- RAG 历史消息检索

---

## 10. 验收标准与成功指标

### 10.1 MVP 功能验收（按 Phase）

| Phase | 验收项 | 通过标准 |
|---|---|---|
| P1 | 登录 | 账号密码登录、3 次失败锁定、JWT 刷新 |
| P1 | Chat 界面 | 会话列表、新建/重命名/删除、切换 |
| P1 | 发票上传 | 输入框选文件 → **立刻**调 `POST /files/upload` 落 MinIO（不阻塞文本输入） → 用户点发送：`POST /chat/stream` JSON 体带 `file_url`+`file_hash`，由 LLM 决定调用 OCR → 右栏持久展示 → 编辑 → 归档全链路 |
| P1 | 发票去重 | 同代码+号码重复归档时阻断 |
| P2 | 合同审查 | 解析 → 脱敏 → 审查 → 风险等级展示 |
| P2 | RAG 知识库 | 文档上传、切分、向量化、检索测试 |
| P2 | 摘要/记忆 | 长会话可正确召回"上次那张发票" |
| P3 | 制度问答 | RAG 召回 + LLM 回答 + 来源引用 |
| P3 | LLM 设置 | 多场景模型配置、连通性测试 |

### 10.2 性能验收

| 指标 | 目标 |
|---|---|
| OCR 识别 P95 | ≤ 5s |
| 合同审查 P95 | ≤ 15s |
| RAG 问答 P95 | ≤ 3s |
| Chat 首屏 P95 | ≤ 2s |
| 会话切换 P95 | ≤ 500ms |
| 并发会话 | ≥ 200 在线用户 |

### 10.3 准确率验收

| 指标 | 目标 |
|---|---|
| 发票字段识别准确率 | ≥ 95%（核心字段：金额、税号、代码、号码） |
| 合同审查召回率 | ≥ 90%（人工标注 100 份合同测试集） |
| 制度问答引用准确率 | ≥ 90%（引用文档与答案匹配） |
| 用户编辑率 | ≤ 30%（识别后未修改直接归档比例 ≥ 70%） |

### 10.4 业务成功指标

| 指标 | 目标（MVP 上线 3 个月） |
|---|---|
| 月度活跃员工 | ≥ 80% 公司员工 |
| 月度归档发票数 | ≥ 上线前 1.5 倍 |
| 合同审查覆盖率 | ≥ 90%（新签合同全部过审） |
| 财务平均处理时长 | 缩短 ≥ 40% |
| 重复报销发生率 | < 1% |

---

## 11. 错误与异常流程

### 11.1 错误分类

| 级别 | 类别 | 示例 |
|---|---|---|
| 用户错误 | 输入类 | 上传非支持文件、必填字段为空、金额非法 |
| 业务错误 | 校验类 | 发票重复、合同未签字、权限不足 |
| 系统错误 | 依赖类 | OCR 超时、LLM 超时、数据库不可达 |
| 严重错误 | 不可恢复 | 文件丢失、数据损坏、密钥失效 |

### 11.2 用户侧错误处理

| 场景 | 用户提示 | 系统行为 |
|---|---|---|
| 文件格式不支持 | 「请上传 PDF / JPG / PNG / WEBP 文件」 | 阻断，不上传 |
| 文件过大（> 20MB） | 「文件超过 20MB，请压缩或分片上传」 | 阻断 |
| OCR 识别失败 | 「识别失败，请检查图片清晰度后重新上传」 | 保留上传，提供「重新识别」按钮 |
| OCR 置信度低 | 字段标黄 + 「⚠ 识别置信度低，请核对」 | 允许归档但提示 |
| 发票重复 | 「该发票已归档（编号 xxx），是否查看？」 | 阻断归档 |
| LLM 超时 | 「正在处理中，请稍候…」+ 轮询 | 后台继续处理，完成后通知 |
| 权限不足 | 「您无权访问此资源」 | 阻断，记录审计 |
| 网络中断 | 「网络异常，正在重连…」 | 自动重连 3 次 |

### 11.3 系统侧错误处理

**OCR 失败重试**
```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def recognize_with_retry(file_bytes):
    try:
        return await ocr_service.recognize(file_bytes)
    except OCRTimeout:
        # 切换备用 OCR 提供商
        return await fallback_ocr_service.recognize(file_bytes)
    except OCRPermanentError:
        # 标记为不可识别，要求人工处理
        raise InvoiceUnrecognizable()
```

**LLM 降级**
```python
async def llm_call_with_fallback(prompt, scene):
    try:
        return await primary_llm.invoke(prompt, timeout=30)
    except LLMTimeout:
        # 降级到本地模型
        return await local_llm.invoke(prompt)
    except LLMRateLimit:
        # 排队等待
        return await queue_llm_call(prompt, scene)
```

### 11.4 异步任务失败补偿

| 任务 | 失败处理 |
|---|---|
| OCR | 写入消息：「识别失败」，WebSocket 推送，前端展示重试按钮 |
| 合同审查 | 写入消息：「审查超时，已转人工」,列表标红「待处理」 |
| RAG 检索 | 返回「未找到相关制度」，不阻塞对话 |
| 文件上传 | 上传到 99% 失败：保留临时文件 24h，允许断点续传 |

### 11.5 用户取消与回滚

- 侧弹窗「取消」：丢弃本次识别结果，删除临时文件，不写入数据库
- 会话删除：软删（30 天回收站），可恢复；硬删（30 天后）级联清理 messages / memory / embeddings
- 归档后撤回：5 分钟内可撤回，超过需走财务撤回流程（记录审计）

---

## 12. 通知机制

### 12.1 通知通道

| 通道 | 场景 | 实现 |
|---|---|---|
| WebSocket | 异步任务完成、合同高风险、会话状态变更 | FastAPI WebSocket |
| SSE | Agent 流式输出（已有） | StreamingResponse |
| 站内信 | 系统通知、制度更新 | `notifications` 表 + 红点提示 |
| 邮件 | 异步任务严重失败、合同高风险、每日看板 | SMTP（可配置） |

### 12.2 通知类型与优先级

| 类型 | 优先级 | 推送时机 |
|---|---|---|
| OCR 完成 | 低 | 异步任务完成时 |
| 合同审查完成 | 中 | 异步任务完成时 |
| 合同高风险告警 | 高 | 风险等级 = 高时立即 |
| 制度文档更新 | 低 | RAG 文档状态变更 |
| 用户密码即将过期 | 中 | 提前 7 天 |
| 系统维护通知 | 中 | 提前 24 小时 |

### 12.3 WebSocket 消息协议

```json
{
  "type": "ocr_done",
  "session_id": "s456",
  "payload": { "invoice_id": "inv_001", "data": {...} },
  "timestamp": "2026-09-20T10:30:00Z"
}
```

**消息类型**：`ocr_done` / `contract_done` / `contract_high_risk` / `session_locked` / `system_notice`

### 12.4 重连与补拉

- WebSocket 断线：前端自动重连（指数退避，最长 30s）
- 重连后：拉取 `last_event_id` 之后的所有未读事件
- 离线消息：保留 24h，过期清理

### 12.5 通知偏好

- 用户可关闭非关键通知（系统通知、个人偏好）
- 关键通知（合同高风险、安全告警）不可关闭

---

## 13. 审计日志

### 13.1 记录范围

| 操作类型 | 记录字段 |
|---|---|
| 登录 | user_id, IP, UA, 结果, 时间 |
| 登出 | user_id, 时间 |
| 发票上传/归档/编辑/删除 | user_id, invoice_id, 变更前, 变更后 |
| 合同上传/归档/审查/删除 | user_id, contract_id, 变更前, 变更后 |
| 文件下载 | user_id, 资源类型, 资源 ID, 文件名 |
| 知识库变更 | user_id, doc_id, 操作（增/删/改/启停） |
| LLM 配置变更 | user_id, 变更前后配置（敏感字段脱敏） |
| 用户管理 | 操作人, 目标用户, 变更内容 |
| 权限变更 | 操作人, 目标用户/角色, 变更前后 |
| 异常登录 | IP, 账号, 触发原因 |

### 13.2 字段结构

| 字段 | 说明 |
|---|---|
| id | UUID |
| tenant_id | 租户 |
| user_id | 操作人 |
| operation_type | 操作类型枚举 |
| target_type | 资源类型（invoice / contract / user / ...） |
| target_id | 资源 ID |
| before | 变更前值（JSONB） |
| after | 变更后值（JSONB） |
| ip | 来源 IP |
| ua | User-Agent |
| result | success / failure |
| error_message | 失败原因 |
| created_at | 时间戳 |

### 13.3 查询与导出

- 后台「审计日志」菜单：按时间、用户、操作类型筛选
- 财务/管理员可见，保留 1 年
- 支持导出 Excel（管理员权限）

### 13.4 不可篡改

- 审计日志仅追加，不允许 UPDATE / DELETE
- 每周生成哈希快照，存入 WORM 存储（对象存储启用 Object Lock）

---

## 14. 权限模型细化

### 14.1 角色能力矩阵

| 能力 | 员工 | 财务 | 管理员 |
|---|---|---|---|
| 查看自己的发票 | ✓ | ✓ | ✓ |
| 查看全部发票 | — | ✓ | ✓ |
| 查看自己的合同 | ✓ | ✓ | ✓ |
| 查看全部合同 | — | ✓ | ✓ |
| 上传发票/合同 | ✓ | ✓ | ✓ |
| 归档发票 | ✓（本人） | ✓ | ✓ |
| 撤销归档 | — | ✓（5 分钟内） | ✓ |
| 重新审查合同 | — | ✓ | ✓ |
| 下载原件 | ✓（本人） | ✓ | ✓ |
| 导出 Excel | — | ✓ | ✓ |
| 用户管理 | — | — | ✓ |
| 知识库管理 | — | — | ✓ |
| LLM 设置 | — | — | ✓ |
| 审计日志 | — | ✓（查看） | ✓（查看+导出） |
| 系统配置 | — | — | ✓ |

### 14.2 权限校验实现

**查询层强制注入**
```python
def query_invoices(user, filters):
    q = select(Invoice).where(Invoice.tenant_id == user.tenant_id)
    if user.role == "employee":
        q = q.where(Invoice.user_id == user.id)
    if filters.get("uploaded_by"):
        q = q.where(Invoice.user_id == filters["uploaded_by"])
    return q
```

**API 层依赖**
```python
@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: UUID,
    user: User = Depends(get_current_user),
):
    invoice = await invoice_service.get(invoice_id, user)
    if not invoice:
        raise HTTPException(403, "无权访问")
    return invoice
```

### 14.3 字段级权限

| 字段 | 员工 | 财务 | 管理员 |
|---|---|---|---|
| 发票备注 | 本人可看可改 | 可看不可改 | 可看可改 |
| 合同关键条款 | 本人可看 | 可看 | 可看 |
| 合同审查评分 | — | 可看可改 | 可看可改 |
| 用户密码哈希 | — | — | 可重置（不可看明文） |
| LLM API Key | — | — | 脱敏显示（前后 4 位） |

### 14.4 多租户预留

- 所有表 `tenant_id NOT NULL`
- 所有查询强制带 `tenant_id`
- 管理员角色可后续扩展为「租户管理员」（跨租户）
- 当前 MVP 单租户，但代码层不写死

---

## 15. 私有化交付物料

### 15.1 部署包

| 物料 | 内容 |
|---|---|
| Docker Compose | 一键启动全套服务（API、Worker、DB、Redis、MinIO） |
| 离线安装包 | 内嵌所有 Python/Node 依赖，无外网环境可用 |
| 初始化脚本 | 数据库迁移 + 种子数据（默认规则文档、角色权限） |
| 配置文件模板 | `.env.example`，覆盖密钥、API Key、Base URL |

### 15.2 初始化数据

**默认 RAG 文档**
- 通用合规规则（tenant_id = NULL）
- 默认报销制度（tenant_id = NULL）
- 默认差旅补贴（tenant_id = NULL）
- 默认合同模板（tenant_id = NULL）

**默认账号**
- admin / 初始密码（首次登录强制修改）
- 财务 / 财务 / 员工示例账号各 1 个

**默认配置**
- LLM 默认选型（GPT-4o / 通义千问，可改）
- OCR 默认腾讯云

### 15.3 升级方案

- 数据库迁移：Alembic 自动检测 + 手动确认
- 代码升级：滚动重启（Worker 先停）
- RAG 文档升级：后台手动触发重新向量化
- 回滚：保留上一版本镜像 + 数据库备份

### 15.4 数据迁移（从老系统导入）

- 提供 Excel 导入工具（管理员后台）
- 字段映射配置（UI 引导）
- 导入预览 + 试导入（100 条）
- 完整导入 + 校验报告

---

## 16. 用户引导

### 16.1 首次进入

**员工首次进入 Chat**
- 弹出欢迎卡片：3 个示例（上传发票、查差旅、上传合同）
- 点击示例 → 模拟演示（不真上传）
- 「跳过引导」按钮

**财务首次进入后台**
- 引导：先创建部门 → 再导入员工 → 再配置知识库
- 进度条显示完成度

**管理员首次进入**
- 引导：上传第一批 RAG 文档 → 测试问答 → 配置 LLM
- 「前往 LLM 设置」直接跳转

### 16.2 空状态

| 场景 | 空状态文案 + 行动按钮 |
|---|---|
| 无会话 | 「开始第一次对话吧」+「新建会话」 |
| 无发票归档 | 「还没有发票，上传一张试试」+「上传发票」 |
| 无合同归档 | 「还没有合同，上传一份试试」+「上传合同」 |
| 知识库为空 | 「知识库为空，上传制度文档」+「上传文档」 |
| 检索无结果 | 「未找到相关制度，尝试换个问法」 |

### 16.3 帮助文档

- 右上角「?」按钮 → 帮助中心
- 帮助中心包含：常见问题、视频教程、联系管理员
- 用户可对回答点「有用 / 无用」，驱动迭代

### 16.4 错误引导

- 识别失败 → 显示常见原因 + 解决方案
- 权限不足 → 显示申请权限入口
- LLM 不可用 → 显示备用方案

---

## 17. 移动端与可访问性

### 17.1 移动端策略

**MVP 阶段**：Web 响应式适配（≥ 768px 桌面布局，< 768px 简化布局）
- 移动端功能：登录、Chat 浏览、查看归档列表
- 移动端不支持：上传（提示「请在电脑端上传」）、后台管理

**后续阶段**：原生或 PWA（待评估）

### 17.2 响应式断点

| 断点 | 设备 | 布局 |
|---|---|---|
| < 640px | 手机 | 单列，会话列表折叠为抽屉 |
| 640-1024px | 平板 | 会话列表 + Chat 双列 |
| ≥ 1024px | 桌面 | 三列（会话列表 + Chat + 侧弹窗） |

### 17.3 可访问性（WCAG 2.1 AA）

- **键盘导航**：Tab 顺序合理，所有操作可纯键盘完成
- **屏幕阅读器**：ARIA 标签完整，会话切换有 Aria-live 通知
- **色彩对比度**：文字 ≥ 4.5:1，大文字 ≥ 3:1
- **焦点可见**：自定义焦点环，不使用 `outline: none`
- **替代输入**：支持语音输入（Web Speech API，可选）
- **错误提示**：除颜色外，配合图标 + 文字

### 17.4 国际化（预留）

- MVP 阶段：中文简体
- 预留 i18n 框架（react-i18next）
- 文案集中在 `locales/zh-CN.json`
- 后续扩展英文 / 繁体

---

## 18. 术语表

| 术语 | 定义 |
|---|---|
| Tenant | 租户，私有化部署下默认为单一企业 |
| Session | 会话，用户与 Agent 的连续对话单元 |
| Message | 消息，会话内的单条对话（用户或 Agent） |
| Tool | 工具，Agent 可调用的能力（OCR / RAG / 审查） |
| RAG | 检索增强生成，结合知识库检索的 LLM 生成 |
| Sidepanel | 侧弹窗，展示结构化识别结果 |
| Stream | 流式输出，Agent 回复逐字推送给前端 |
| Embedding | 向量化，文本转为向量用于相似度检索 |

---

## 19. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0 | 2026-09-20 | 初版，覆盖产品定位、功能模块、用户旅程、数据模型 |
| V1.1 | 2026-09-21 | **Phase A 完成**：发票 OCR 归档全链路验收（详见 §20） |
| V1.2 | 2026-09-23 | **Phase A+ UI/UX 增量**：shadcn/ui 全面替换手搓控件、LLM 设置编辑体验优化、错误提示与消息渲染重构、DeepSeek 风格会话侧栏（详见 §21） |
| V1.3 | 2026-09-25 | **识别主路径切换**：大模型同步识别发票并按附件分流；附件回显；场景级 system_prompt；虚拟机 Docker 部署与运行手册（详见 §22） |

---

## 20. Phase A 验收清单（2026-09-21）

**范围**：发票智能识别 + 人工确认 + 归档（旅程一）。

### 20.1 端到端流程

```
用户上传 → chat_stream multipart → MinIO 存 + SHA-256
  → Celery process_invoice_ocr → 腾讯云 OCR（或 Mock 降级）
  → InvoiceOCRResult → invoice_service.create_pending(status='pending_review')
  → 前端轮询 GET /invoices/preview/by-hash/{hash}
  → 用户编辑 → POST /invoices/{id}/confirm → status='active'
  → 档案页可见
```

### 20.2 验收项

| # | 验收点 | 验证方式 | 状态 |
|---|---|---|---|
| 1 | 上传 PDF/JPG → SSE 收到 `sidepanel{status:processing}` + `done` | smoke.sh step 10 + test_chat_with_file | ✅ |
| 2 | 3-10s 后前端 InvoicePanel 弹出可编辑表单 | 轮询 `/preview/by-hash/{hash}` 拿到 ready | ✅ |
| 3 | 编辑字段 → 点确认 → toast 成功 + 档案列表刷新 | `invoiceApi.confirm(id, data)` | ✅ |
| 4 | 重复上传相同 (code+number) 发票 → 后端 409 | `uq_invoice_tenant_code_number` 唯一约束 | ✅ |
| 5 | 员工看不到别人的发票 | 行级 `WHERE user_id = current_user.id` | ✅ |
| 6 | 软删 → 列表不显示 | status='deleted' 过滤 | ✅ |
| 7 | 详情页拿 MinIO 预签名 URL 下载原件 | `GET /invoices/{id}/file` | ✅ |
| 8 | LLM 设置编辑 system_prompt → 持久化 | `llm_configs.system_prompt` 列 + 迁移 002 | ✅ |
| 9 | 测试全绿 | `pytest tests/test_invoice_archive.py tests/test_chat_with_file.py` | ✅ |
| 10 | smoke.sh 11 步全绿 | 见 scripts/smoke.sh | ✅ |
| 11 | Celery worker 自动接管 OCR 任务 | docker-compose worker 已挂载 | ✅ |

### 20.3 关键设计决策

1. **不用 Redis pubsub**：前端轮询 `GET /invoices/preview/by-hash/{hash}`，避免长 SSE + 重连复杂度。
2. **两阶段入库**：OCR 完成先 `status='pending_review'`，用户确认才 `active`，符合"AI 做识别，人做确认"原则。
3. **去重策略**：硬拒绝（409 Conflict），不静默覆盖。重复上传时 OCR 任务主动跳过。
4. **降级策略**：`TENCENT_OCR_SECRET_ID` 为空时返回 `MockOCRProvider`，开发环境无需真密钥。
5. **审计日志**：编辑/确认/删除均写入 `audit_logs`，记录 `before_value` / `after_value` 快照。
6. **行级权限**：员工只查自己发票，财务/管理员查全部；service 层用 `user.role` 强制过滤。

### 20.4 不在 Phase A 范围

- 流式中断（`/chat/interrupt/{id}` 仍 MVP 占位）
- LLM 归一（`_llm_normalize` 当前直接透传 OCR 结果；scene='ocr_post' 留给 Phase B）
- 批量上传 / 拖拽上传 UI
- 发票字段版本历史（仅快照当前值）
- PDF 多页发票拆分识别

---

## 21. Phase A+ UI/UX 增量（2026-09-23）

**定位**：Phase A 验收之后、Phase B 启动之前的「打磨批次」。不改主链路、不动数据模型，只对 **管理后台 + 会话界面** 做工程化与体验升级。共 4 个提交：

```
7a2a835 用 shadcn/ui 替换原生 confirm/prompt 及手搓下拉菜单，新增 AGENT.md
69725e3 LLM 配置编辑：API Key 输入 + system_prompt 持久化
2a7f868 编辑态 LLM 连通性测试 + 错误提示 / 消息渲染优化
a8ea2b7 会话侧栏重构为 DeepSeek 风格：时间桶分组 + 用户底部信息条
```

### 21.1 UI 控件体系统一（7a2a835）

**目标**：把过去散落的手搓控件（`onMouseLeave` 下拉、原生 `confirm/prompt/alert`、`<select>`、手搓 checkbox / dialog）全部替换为 shadcn/ui，新增 [`AGENT.md`](AGENT.md) 工程规约强制后续提交遵守。

**改动摘要**：

| 旧形态 | 新形态 | 文件 |
|---|---|---|
| 原生 `confirm()` 删会议 / 会话 / 消息 | `AlertDialog` + `AlertDialogAction` / `AlertDialogCancel` | [`alert-dialog.tsx`](frontend/src/components/ui/alert-dialog.tsx) |
| 原生 `prompt()` 重命名会话 | `Dialog` + `Input` + 受控 state | [`dialog.tsx`](frontend/src/components/ui/dialog.tsx) + [`input.tsx`](frontend/src/components/ui/input.tsx) |
| 原生 `alert()` | shadcn `Toast` / `Badge` 替代 | — |
| 手搓 `<select>` | `Select` + `SelectTrigger` + `SelectContent` + `SelectItem` | [`select.tsx`](frontend/src/components/ui/select.tsx) |
| 手搓 onMouseLeave 菜单 | `DropdownMenu` + `DropdownMenuContent` | [`dropdown-menu.tsx`](frontend/src/components/ui/dropdown-menu.tsx) |
| 手搓居中弹窗 | `Dialog` | [`dialog.tsx`](frontend/src/components/ui/dialog.tsx) |
| 手搓侧滑面板 | `Sheet`（`SidePanel` 已废弃，标注于 [`AGENT.md §2`](AGENT.md)） | [`sheet.tsx`](frontend/src/components/ui/sheet.tsx) |

**关键设计决策**：

1. **AGENT.md 作为"工程规约"存在**：所有后续 UI 改动必须先读 [`AGENT.md`](AGENT.md)；新增 UI 控件必须基于 Radix + CVA + tailwindcss-animate 写到 `components/ui/`。
2. **`SidePanel` 弃用但保留旧文件**：避免大爆炸重写；新代码强制用 `Sheet`。
3. **`Login` 玻璃拟态卡片保留**：品牌一致性大于控件统一。

### 21.2 LLM 配置编辑体验（69725e3）

**目标**：让管理员在「LLM 设置」对话框里能完整地配置一个场景，不再需要去数据库改 `llm_configs`。

**新增能力**：

- **API Key 显式输入框**：旧版本只读 + 占位 `****xxxx`，管理员必须直连数据库才能换 key；现在用 `<Input type="password">` 显式录入，明文提交到后端，后端负责加密落盘 [`api_key_encrypted`](backend/app/models/__init__.py)。
- **`system_prompt` 多行文本**：场景级 prompt 直接在 UI 里编辑，持久化到 `llm_configs.system_prompt`（迁移 `002_invoice_dedup_and_system_prompt.py`）。
- **未填字段保留旧值**：API Key 输入框为空 = 不动原 key；system_prompt 为空字符串 → 后端存 `NULL`。

**改动文件**：

- [`frontend/src/components/admin/LLMSettings.tsx`](frontend/src/components/admin/LLMSettings.tsx)：表单 `EditState` 扩展 `api_key_input` + `system_prompt`，提交时分别处理。
- [`backend/app/services/llm_config_service.py`](backend/app/services/llm_config_service.py)：update 路径区分「仅更新元数据」「更新 API Key」「更新 system_prompt」三种 case。
- [`frontend/src/api/admin.ts`](frontend/src/api/admin.ts) + [`frontend/src/types/index.ts`](frontend/src/types/index.ts)：类型补齐。

### 21.3 编辑态连通性测试 + 错误提示（2a7f868）

**目标**：管理员编辑 LLM 配置时就能验证连通性，不用保存后再去对话窗口试错。

**新增能力**：

- 「测试连接」按钮在编辑态可点 → 触发 `/admin/llm/configs/{id}/test`（临时用表单值拼装请求，不写库）。
- 错误分级：
  - `4xx`：参数错误 → toast 高亮字段 + 红框
  - `5xx`：服务端异常 → toast + 重试入口
  - 网络断：`fetch` reject → 「请检查网络」+ 重试入口
- 流式消息渲染：把通用 SSE 解析抽到 [`StreamRenderer`](frontend/src/components/chat/StreamRenderer.tsx)，错误事件统一渲染为带复制按钮的错误块。

### 21.4 DeepSeek 风格会话侧栏（a8ea2b7）

**目标**：会话列表视觉与交互对齐 DeepSeek / ChatGPT 风格（时间桶分组 + 顶栏用户区）。

**改动要点**：

- **时间桶**：按 `今天 / 昨天 / 本周 / 本月 / 更早` 分组，会话项 hover 显示完整时间。
- **用户底部信息条**：侧栏底部固定一条用户卡片（头像 + 邮箱 + 设置入口），不再依赖顶栏 Avatar Dropdown。
- **会话项**：左侧 icon 区（"普通对话" / "OCR" / "审查" 三种状态色），右侧"更多"菜单（`DropdownMenu`：重命名 / 删除）。
- **状态库**：[`sessionStore.ts`](frontend/src/stores/sessionStore.ts) 增加 `groupByTimeBucket()` 纯函数 + `activeSessionId` 选择器；UI 用 Zustand 订阅。

**改动文件**：[`SessionList.tsx`](frontend/src/components/chat/SessionList.tsx)（侧栏主体）、[`sessionStore.ts`](frontend/src/stores/sessionStore.ts)（状态层）、[`uiStore.ts`](frontend/src/stores/uiStore.ts)（侧栏折叠状态）、[`Chat.tsx`](frontend/src/pages/Chat.tsx)（整体布局调整）。

### 21.5 验收

| # | 验收点 | 验证方式 | 状态 |
|---|---|---|---|
| 1 | `AGENT.md` 规约与代码现状一致 | §2 / §8 清单可对照 | ✅ |
| 2 | 旧 `confirm/prompt/alert` 在 grep 结果中归零 | `rg "confirm\(|prompt\(|alert\(" frontend/src` | ✅ |
| 3 | LLM 设置能填能保存 API Key | 管理后台 → 切换场景 → 保存 → 后端 `api_key_encrypted` 落盘 | ✅ |
| 4 | `system_prompt` 持久化 | DB 列 `llm_configs.system_prompt` 不为空 | ✅ |
| 5 | 编辑态测试连接 | 保存前点「测试连接」→ 看到连通结果 | ✅ |
| 6 | 侧栏时间桶分组渲染正确 | mock 跨多日会话数据 | ✅ |
| 7 | 前端 `tsc --noEmit` + `npm run build` 全绿 | 见 [`AGENT.md §6`](AGENT.md) | ✅ |

### 21.6 不在 Phase A+ 范围

- 新的业务功能（合同审查 / RAG 知识库 / 制度问答 → Phase B）
- 后端架构改动（Celery / MinIO / pgvector 均未触碰）
- 数据模型扩展（除 `llm_configs.system_prompt` 列外无新表 / 新字段）
- 移动端适配（仍沿用桌面端 `≥ 768px` 布局约束）

---

## 22. 当前进度（2026-09-25）

**定位**：Phase A 发票归档链路保留。识别从「腾讯云 OCR + Celery 异步 + 前端轮询」改为「大模型同步识别，SSE 直接推侧栏」。§20 记录的是当时的验收事实；下面是现在的主路径。

### 22.1 端到端流程（现行）

```
选文件 → POST /files/upload 落 MinIO（选完即传）
  → 发送 POST /chat/stream（JSON：message + file_url + file_hash）
  → 大模型 classify：invoice | contract | chat
  → invoice：多模态/抽文本识别 → 入库 pending_review → SSE sidepanel + 带字段回复
  → contract：合同审查场景模型文本审查（未归档、无 RAG）
  → chat：日常对话场景带着文件内容回答
  → 用户确认发票 → status=active
```

图片走 `image_url`；PDF/Word 先抽文本再交给同一模型。单据识别场景没有密钥时，改用日常对话里已配置的模型。两条都没有密钥则直接报错，不再回落 OCR 或 Mock。

### 22.2 已完成

| # | 事项 | 说明 | 状态 |
|---|---|---|---|
| 1 | 大模型同步识别发票 | `invoice_vision_service.recognize()`，source 固定 `llm`；至少要有发票号码或价税合计 | ✅ |
| 2 | 上传分流 | `classify()` 返回 invoice / contract / chat | ✅ |
| 3 | 附件回显 | `POST /files/presign`；消息 `attachments`；气泡预览；可只发附件 | ✅ |
| 4 | 场景级 system_prompt | 有配置则替换默认人设，读取失败回落默认 | ✅ |
| 5 | LLM 设置编辑区 | 对话框 `max-w-3xl`，提示词输入约 14 行 | ✅ |
| 6 | 虚拟机部署 | Ubuntu Docker，`scripts/deploy-vm.sh`；手册 `docs/backend-runbook.md` | ✅ |
| 7 | 本机前端代理 | `vite.config.ts` 用 `loadEnv` 读取 `VITE_API_PROXY_TARGET` | ✅ |
| 8 | 缺陷修复 | 审计日志 `before`/`after`；422 用 `jsonable_encoder`；smoke.sh 与 JSON 上传对齐 | ✅ |
| 9 | 烟测 | `scripts/smoke.sh`：14 通过 / 0 失败 / 0 警告 | ✅ |

相关提交：`67fa1e7`、`2753687`、`2c2655a`、`8fdb8d9`、`3e81369`、`1c51e93`。

### 22.3 未完成

| 项 | 说明 |
|---|---|
| LLM 凭证 | 虚拟机根 `.env` 的各场景 API Key 仍需自行填写，否则对话与识别返回缺凭证 |
| 合同归档与合规 RAG | 当前只是审查场景的一次文本回复，没有风险等级入库和规则检索 |
| 知识库 / 制度问答 | Phase 2 / Phase 3，未开始交付 |
| 会话摘要与结构化记忆 | Phase 2，未开始交付 |
| Celery OCR 任务 | 代码仍在，主链路不再 `.delay()`，后续可删或改作补偿任务 |

### 22.4 与 §20 的差异

| §20 当时 | 现在 |
|---|---|
| Celery `process_invoice_ocr` 异步识别 | 请求内同步识别并推 SSE |
| 腾讯云 OCR，无密钥走 Mock | 只用已配置的大模型，无密钥即失败 |
| 前端轮询 `/invoices/preview/by-hash/{hash}` 等结果 | 识别完成即推 `sidepanel`；轮询接口仍可用 |
| 合同审查不在范围 | 分流已接到审查场景，归档与 RAG 仍未做 |

---