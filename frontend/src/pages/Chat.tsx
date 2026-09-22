import { SessionList } from '@/components/chat/SessionList'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBox } from '@/components/chat/InputBox'
import { StreamRenderer } from '@/components/chat/StreamRenderer'
import { InvoicePanel } from '@/components/sidepanel/InvoicePanel'
import { ContractPanel } from '@/components/sidepanel/ContractPanel'

/**
 * 对话工作台 — DeepSeek 风格双栏布局
 *
 * 顶栏已下沉到 SessionList 底部（用户信息 / 后台 / 登出），
 * 整页只剩：左侧会话栏 + 右侧对话区。
 */
export function Chat() {
  return (
    <div className="flex h-screen bg-canvas text-ink">
      <SessionList />

      <main className="flex flex-1 flex-col min-w-0 bg-canvas">
        <StreamRenderer />
        <ChatWindow />
        <InputBox />
      </main>

      <InvoicePanel />
      <ContractPanel />
    </div>
  )
}