# Finance Frontend

React + TypeScript 前端 - 企业财务 AI Agent 平台。

## 启动

```bash
# 方式一：Docker
docker-compose up frontend

# 方式二：本地
npm install
npm run dev
```

访问 http://localhost:5173

## 目录结构

```
frontend/
├── src/
│   ├── api/           # API 客户端（Axios + SSE）
│   ├── components/
│   │   ├── ui/        # shadcn/ui 组件
│   │   ├── chat/      # Chat 相关组件
│   │   ├── sidepanel/ # 侧弹窗（发票/合同）
│   │   └── admin/     # 后台管理组件
│   ├── pages/         # 页面（Login/Chat/Admin）
│   ├── stores/        # Zustand 状态管理
│   ├── hooks/         # 自定义 Hooks
│   ├── lib/           # 工具函数 + 校验
│   ├── types/         # TS 类型
│   ├── App.tsx
│   └── main.tsx
├── index.html
├── vite.config.ts
├── tailwind.config.ts
└── package.json
```

## 脚本

```bash
npm run dev          # 开发（热重载）
npm run build        # 生产构建
npm run preview      # 预览生产构建
npm run lint         # ESLint
npm run format       # Prettier
npm run test         # 单元测试（Vitest）
npm run test:e2e     # E2E（Playwright）
```

## 技术栈

- React 18 + TypeScript
- Vite（构建）
- TailwindCSS + shadcn/ui（样式）
- Zustand（状态）
- React Router（路由）
- React Hook Form + Zod（表单）
- TanStack Query（数据）
- Axios（HTTP）
- SSE（流式响应）
- Recharts（图表）

## 状态管理

- `authStore`: 登录态、用户信息
- `sessionStore`: 会话列表、消息（按 sessionId 隔离）
- `uiStore`: 侧弹窗、流式状态

## SSE 流式

Chat 流式响应通过 `streamChat()` 异步生成器解析，事件类型：
- `text`: 增量文本
- `sidepanel`: 触发侧弹窗
- `done`: 流结束
- `error`: 错误