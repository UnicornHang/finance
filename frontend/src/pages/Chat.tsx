import { PanelLeftOpen } from 'lucide-react'

import { SessionList } from '@/components/chat/SessionList'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBox } from '@/components/chat/InputBox'
import { StreamRenderer } from '@/components/chat/StreamRenderer'
import { InvoicePanel } from '@/components/sidepanel/InvoicePanel'
import { ContractPanel } from '@/components/sidepanel/ContractPanel'
import { useUIStore } from '@/stores/uiStore'

/**
 * 对话工作台 — DeepSeek 风格双栏布局
 *
 * 顶栏已下沉到 SessionList 底部（用户信息 / 后台 / 登出），
 * 整页只剩：左侧会话栏 + 右侧对话区。
 * 侧栏可整体收起 —— 收起后主区顶部展示一个浮动按钮用于展开。
 */
export function Chat() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)

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

      <InvoicePanel />
      <ContractPanel />
    </div>
  )
}