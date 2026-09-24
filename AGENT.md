# AGENT.md — 项目工程规约（AI 协作与代码生成）

> 本文件是给所有 AI / 人类工程师共同遵守的工程规约。阅读本文件后，**所有 UI 改动与新增代码必须遵循以下约定**。

---

## 1. 总则

- **任何能在 shadcn/ui 中实现的 UI，必须使用 shadcn/ui 模式**。
  - 不允许新增裸 `<div className="rounded border ...">` 这类手搓的卡片 / 弹窗 / 下拉 / 复选等。
  - 不允许新增 Tailwind UI / daisyui / MUI / Ant Design 等其他 UI 体系依赖。
  - 所有 UI 控件必须放到 [`frontend/src/components/ui/`](frontend/src/components/ui/) 下，命名遵循 shadcn 习惯（小写、kebab-case 文件名，单词 PascalCase 导出）。

- **新组件路径规范**：每个组件单独成文件，例如 `checkbox.tsx` 导出 `Checkbox`，`dropdown-menu.tsx` 导出 `DropdownMenu*`。
- **不要重写 shadcn 已有的导出**：如果要"样式调整"，改 `tailwind.config.ts` 主题 token 或 `index.css` 里的 CSS 变量，而不是在调用处覆盖大量 className。

---

## 2. 已有 shadcn/ui 组件清单（截至本规约）

文件 → 主要导出（全部基于 Radix Primitives + CVA）：

| 文件 | 导出 | 适用场景 |
| --- | --- | --- |
| [`button.tsx`](frontend/src/components/ui/button.tsx) | `Button` | 所有按钮操作（variant: primary/secondary/ghost/link/danger/danger-outline；size: sm/md/lg/xl/icon/icon-sm）|
| [`input.tsx`](frontend/src/components/ui/input.tsx) | `Input`, `Textarea` | 文本输入、多行文本 |
| [`label.tsx`](frontend/src/components/ui/label.tsx) | `Label` | 表单字段标题（基于 @radix-ui/react-label）|
| [`select.tsx`](frontend/src/components/ui/select.tsx) | `Select`, `SelectGroup`, `SelectValue`, `SelectTrigger`, `SelectContent`, `SelectItem`, `SelectLabel`, `SelectSeparator` | 下拉选择（**禁止**再用 native `<select>`）|
| [`checkbox.tsx`](frontend/src/components/ui/checkbox.tsx) | `Checkbox` | 复选框（基于 @radix-ui/react-checkbox）|
| [`separator.tsx`](frontend/src/components/ui/separator.tsx) | `Separator` | 水平/垂直分割线 |
| [`card.tsx`](frontend/src/components/ui/card.tsx) | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardAction`, `CardContent`, `CardFooter` | 容器卡片 |
| [`dialog.tsx`](frontend/src/components/ui/dialog.tsx) | `Dialog`, `DialogTrigger`, `DialogPortal`, `DialogClose`, `DialogOverlay`, `DialogContent`, `DialogHeader`, `DialogFooter`, `DialogTitle`, `DialogDescription` | 居中模态框 |
| [`alert-dialog.tsx`](frontend/src/components/ui/alert-dialog.tsx) | `AlertDialog`, `AlertDialogTrigger`, `AlertDialogPortal`, `AlertDialogOverlay`, `AlertDialogContent`, `AlertDialogHeader`, `AlertDialogFooter`, `AlertDialogTitle`, `AlertDialogDescription`, `AlertDialogAction`, `AlertDialogCancel` | **必须等待用户确认的破坏性操作**（替代原生 `confirm()`）|
| [`sheet.tsx`](frontend/src/components/ui/sheet.tsx) | `Sheet`, `SheetContent`（side: top/right/bottom/left）, `SheetHeader`, `SheetTitle`, `SheetDescription`, `SheetFooter`, `SheetOverlay` | 侧滑面板（替代过去的 `SidePanel`）|
| [`dropdown-menu.tsx`](frontend/src/components/ui/dropdown-menu.tsx) | `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuItem`（variant: default/destructive）, `DropdownMenuLabel`, `DropdownMenuSeparator`, `DropdownMenuGroup`, `DropdownMenuSub`, `DropdownMenuCheckboxItem`, `DropdownMenuRadioItem`, `DropdownMenuShortcut` | 下拉菜单（**禁止**再用 onMouseLeave toggle 的手搓 div）|
| [`badge.tsx`](frontend/src/components/ui/badge.tsx) | `Badge`（CVA 变体 tone: success/primary/warning/danger/neutral/outline；shape: pill/square；可选 `dot`）| 状态徽章 |
| [`surface.tsx`](frontend/src/components/ui/surface.tsx) | `Field`（label + error + hint + required 字段组合）| 表单字段容器（注意：`SidePanel` 已废弃，请改用 `Sheet`）|
| [`table.tsx`](frontend/src/components/ui/table.tsx) | `Table`, `THead`, `TBody`, `TR`, `TH`, `TD`, `Toolbar`, `EmptyState` | 数据表与工具栏 |
| [`stat.tsx`](frontend/src/components/ui/stat.tsx) | `StatCard`, `SectionHeader` | 财务 KPI 与页面区块标题（领域组件，保留）|
| [`brand.tsx`](frontend/src/components/ui/brand.tsx) | `BrandLogo` | 品牌 Logo（领域组件，保留）|

---

## 3. 写新组件时的硬性要求

### 3.1 组件结构
- **必须** 使用 `React.forwardRef` 暴露 `ref`（shadcn 标准）。
- **必须** 在根元素上加 `data-slot="xxx"`，便于样式覆盖与测试识别。
- **必须** 通过 `cn()`（来自 `@/lib/utils`，封装 `clsx + tailwind-merge`）合并 className，避免重复与冲突。
- **必须** 支持透传 `...props`，让消费者覆盖原生属性。

### 3.2 样式
- **圆角**：使用 Tailwind 主题 token（`rounded-md`/`rounded-lg`），**不要**写死 `rounded-[4px]` 等魔数。
- **颜色**：使用 `bg-surface`/`border-line`/`text-ink`/`ring-primary` 等项目 token，或 shadcn 兼容别名 `bg-background`/`border-input`/`ring-ring`。
- **焦点环**：必须使用 `focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas`，与全局一致。
- **图标尺寸**：按钮内 SVG 用 `[&_svg]:size-4 [&_svg]:shrink-0` 强制统一，不要每处重复 `className="h-4 w-4"`。
- **动画**：使用 `data-[state=open]:animate-in` + `tailwindcss-animate` 提供的 keyframes，不要自己写 transition。

### 3.3 表单组件
- 任何 `<Input>` / `<Textarea>` / `<Select>` 都要用对应的 `<Label>` 包裹（通过 `htmlFor` 或 Radix Label 的自动关联）。
- 与 react-hook-form 集成的非原生组件（Select、Checkbox 等），**必须** 用 `<Controller>` 包装，禁止用 `register()`。

### 3.4 弹窗 / 抽屉 / 下拉
- 居中弹窗用 `Dialog` 系列。
- 侧滑面板用 `Sheet` 系列（`side="right"` 为最常用）。
- 下拉菜单用 `DropdownMenu` 系列，**禁止**手搓 `onMouseLeave={() => setOpen(false)}` 的 div。
- 表单提交类按钮要 `type="button"` 显式声明，避免在父级 `<form>` 里意外触发 submit。

---

## 4. 严禁的反模式

```tsx
// ❌ 禁止：手搓下拉
<div className="relative">
  <button onClick={() => setOpen(!open)}>菜单</button>
  {open && <div className="absolute ..." onMouseLeave={...}>...</div>}
}

// ❌ 禁止：native select
<select className="..."><option /></select>

// ❌ 禁止：手搓卡片
<div className="rounded-lg border border-line bg-surface p-5">...</div>

// ❌ 禁止：原生 checkbox
<input type="checkbox" className="rounded ..." />

// ❌ 禁止：手搓弹窗
<div className="fixed inset-0 z-50 bg-black/50">...</div>

// ❌ 禁止：原生 confirm()/prompt()/alert()
if (!confirm('确定删除？')) return
const v = prompt('重命名')
alert('已保存')

// ❌ 禁止：重复魔数样式
<button className="h-9 px-4 rounded bg-blue-500 text-white">保存</button>
```

---

## 5. 何时新增组件

| 场景 | 是否允许新增组件 | 备注 |
| --- | --- | --- |
| 业务专用复合组件（如 `RiskBadge`）| ✅ | 放在 `components/<feature>/` 下，不要污染 `ui/` |
| 通用 UI（Switch、RadioGroup、Tooltip、Tabs、Popover、Accordion 等）| ✅ | 必须以 shadcn 模式实现（基于 Radix + CVA + tailwindcss-animate），导出到 `components/ui/` |
| 私有的"一次性"样式盒子 | ❌ | 改用现有 Card + Tailwind 组合类 |

---

## 6. 验证步骤

任何 UI 改动后**必须**完成以下检查：

```bash
cd frontend
npx tsc --noEmit         # 类型检查
npm run build            # Vite 构建（产出 dist/）
```

构建失败、类型错误、警告中残留未使用变量 → 不允许合并。

---

## 7. 命名与目录约定速查

```
frontend/src/
├── components/
│   ├── ui/                       # shadcn 风格通用 UI
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── checkbox.tsx
│   │   ├── dialog.tsx
│   │   ├── dropdown-menu.tsx
│   │   ├── input.tsx
│   │   ├── label.tsx
│   │   ├── select.tsx
│   │   ├── separator.tsx
│   │   ├── sheet.tsx
│   │   ├── surface.tsx           # Field 字段组合（SidePanel 已废弃）
│   │   ├── badge.tsx
│   │   ├── stat.tsx              # 财务 KPI（领域组件）
│   │   ├── brand.tsx             # 品牌 Logo（领域组件）
│   │   └── table.tsx
│   ├── admin/                    # 后台业务页
│   ├── chat/                     # 对话页
│   └── sidepanel/                # 侧栏面板（已被 Sheet 替代，新代码不要再写）
├── pages/
│   ├── Admin.tsx
│   ├── Chat.tsx
│   └── Login.tsx
├── api/                          # 后端接口客户端
├── hooks/                        # 业务 hooks
├── lib/
│   ├── utils.ts                  # cn() 等
│   ├── validators.ts
│   └── queryClient.ts
├── stores/                       # Zustand 状态
├── types/                        # 共享类型
├── App.tsx
├── main.tsx
└── index.css                     # Tailwind base + shadcn CSS 变量
```

---

## 8. 后续迁移提示

以下组件尚未迁移至 shadcn 模式，**后续提交禁止引入新代码占用这些位置**：

- `Chat` / `ChatWindow` / `InputBox` / `StreamRenderer` 中手写的 message bubble / markdown 容器（领域组件，可保留，但若新增样式必须参考 shadcn 的 `data-slot` 习惯）。
- `LLMSettings` 的"模型"组合下拉是项目特殊形态（type-ahead + 自定义面板），目前保留；但**禁止**复制该模式到其他地方，全部下拉统一走 `Select`。
- `Login` 玻璃拟态卡片是设计系统约定，保留；但表单内所有交互控件一律走 shadcn（已完成）。

---

**最后更新**：2026-09-23（Phase A+ UI/UX 增量批次；§2 表格确认 `alert-dialog` / `dialog` / `dropdown-menu` / `select` / `sheet` 已覆盖全部新增 UI 改动；§8 迁移提示内容与现状一致：`LLMSettings` 模型组合下拉仍按"保留 + 禁止复制"原则维护）。本规约与代码现状同步。每次大规模 UI 改动（如新增 shadcn 组件、修改 Tailwind 主题）后请同步更新本文第 2 节与第 8 节。