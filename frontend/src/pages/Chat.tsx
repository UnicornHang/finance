import { PanelLeftOpen } from 'lucide-react'

import { SessionList } from '@/components/chat/SessionList'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBox } from '@/components/chat/InputBox'
import { StreamRenderer } from '@/components/chat/StreamRenderer'
import { InvoicePanel } from '@/components/sidepanel/InvoicePanel'
import { ContractPanel } from '@/components/sidepanel/ContractPanel'
import { useUIStore } from '@/stores/uiStore'

/**
 * 对话工作台 — 两栏 / 三栏自适应
 *
 * 顶栏已下沉到 SessionList 底部（用户信息 / 后台 / 登出）。
 * 默认布局：左 SessionList + 中对话区（双栏）。
 * 当用户通过"上传发票"按钮或 SSE sidepanel 事件产生 invoice/contract 数据时，
 * 右侧持久化展示结构化面板（三栏）。用户点击面板"关闭"按钮回到两栏。
 *
 * SessionList 可整体收起 —— 收起后主区顶部展示一个浮动按钮用于展开。
 */
export function Chat() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)
  const sidePanelOpen = useUIStore((s) => s.sidePanelOpen)
  const sidePanelType = useUIStore((s) => s.sidePanelType)

  const rightPaneOpen =
    sidePanelOpen && (sidePanelType === 'invoice' || sidePanelType === 'contract')

  return (
    <div className="flex h-screen bg-canvas text-ink">
      <SessionList />

      <main className="relative flex flex-1 flex-col min-w-0 bg-canvas">
        {/* 侧栏收起时：主区顶部左侧浮动一个"展开"按钮 */}
        {sidebarCollapsed && (
          <button
            type="button"
            aria-label="展开侧栏"
            title="展开侧栏"
            onClick={() => setSidebarCollapsed(false)}
            className="absolute left-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-md border border-line bg-surface text-ink-tertiary shadow-hairline hover:bg-surface-inset hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        )}

        <StreamRenderer />
        <ChatWindow />
        <InputBox />
      </main>

      {rightPaneOpen && (
        <aside className="flex w-[360px] shrink-0 border-l border-line bg-surface animate-fade-in sm:w-[400px]">
          {sidePanelType === 'invoice' ? <InvoicePanel /> : <ContractPanel />}
        </aside>
      )}
    </div>
  )
}