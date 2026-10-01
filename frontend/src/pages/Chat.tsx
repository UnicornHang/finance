import { PanelLeftOpen, PanelRightOpen, FileText, Receipt, ChevronDown } from 'lucide-react'

import { SessionList } from '@/components/chat/SessionList'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBox } from '@/components/chat/InputBox'
import { StreamRenderer } from '@/components/chat/StreamRenderer'
import { InvoicePanel } from '@/components/sidepanel/InvoicePanel'
import { ContractPanel } from '@/components/sidepanel/ContractPanel'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useCurrentMessages } from '@/stores/sessionStore'
import { useUIStore } from '@/stores/uiStore'
import {
  listHistoryDocumentTurns,
  openHistoryDocument,
  type HistoryDocumentTurn,
} from '@/lib/sidePanelHistory'

/**
 * 对话工作台 — 两栏 / 三栏自适应
 *
 * 顶栏已下沉到 SessionList 底部（用户信息 / 后台 / 登出）。
 * 默认布局：左 SessionList + 中对话区（双栏）。
 * 当用户上传发票/合同，或切回的会话最后一轮是发票/合同时，
 * 右侧持久化展示结构化面板（三栏）。用户点击面板"关闭"按钮回到两栏，
 * 主区右上角可再点「查看审查/发票」重新打开；多份时用下拉切换。
 */
export function Chat() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed)
  const sidePanelOpen = useUIStore((s) => s.sidePanelOpen)
  const sidePanelType = useUIStore((s) => s.sidePanelType)
  const sidePanelData = useUIStore((s) => s.sidePanelData)
  const reopenSidePanel = useUIStore((s) => s.reopenSidePanel)
  const messages = useCurrentMessages()
  const documentTurns = listHistoryDocumentTurns(messages)
  const activeFileHash =
    (sidePanelData as { file_hash?: string } | null)?.file_hash ?? null

  const rightPaneOpen =
    sidePanelOpen && (sidePanelType === 'invoice' || sidePanelType === 'contract')
  // 关了可重开；多份时面板开着也能下拉切换
  const showDocSwitcher = documentTurns.length > 1
  const canReopenSidePanel =
    !sidePanelOpen &&
    (((sidePanelType === 'invoice' || sidePanelType === 'contract') &&
      sidePanelData != null) ||
      documentTurns.length > 0)

  const openTurn = (turn: HistoryDocumentTurn) => {
    void openHistoryDocument(turn)
  }

  const docMenuButton = (
    <button
      type="button"
      className="absolute right-3 top-3 z-10 inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-body-sm font-medium text-ink-secondary shadow-hairline hover:bg-surface-inset hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      <FileText className="h-3.5 w-3.5 text-primary" />
      {sidePanelOpen ? '切换审查结果' : '查看审查结果'}
      <span className="rounded bg-canvas px-1 text-label-sm text-ink-tertiary tabular-nums">
        {documentTurns.length}
      </span>
      <ChevronDown className="h-3.5 w-3.5 text-ink-tertiary" />
    </button>
  )

  const docMenu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{docMenuButton}</DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <DropdownMenuLabel>本会话识别结果</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {documentTurns.map((turn) => {
          const name = turn.attachment.original_filename || '未命名文件'
          const selected =
            sidePanelOpen && turn.attachment.file_hash === activeFileHash
          return (
            <DropdownMenuItem
              key={`${turn.type}-${turn.attachment.file_hash}-${turn.attachment.id ?? ''}`}
              onSelect={() => openTurn(turn)}
              className={selected ? 'bg-primary-tint text-primary' : undefined}
            >
              {turn.type === 'contract' ? (
                <FileText className="h-4 w-4" />
              ) : (
                <Receipt className="h-4 w-4" />
              )}
              <span className="truncate">{name}</span>
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )

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

        {/* 多份识别结果：始终可切换；单份关闭后可重开 */}
        {showDocSwitcher && docMenu}
        {!showDocSwitcher && canReopenSidePanel && (
          <button
            type="button"
            aria-label={
              documentTurns[0]?.type === 'invoice' || sidePanelType === 'invoice'
                ? '打开发票识别'
                : '打开合同审查'
            }
            title={
              documentTurns[0]?.type === 'invoice' || sidePanelType === 'invoice'
                ? '打开发票识别'
                : '打开合同审查'
            }
            onClick={() => {
              if (documentTurns[0]) openTurn(documentTurns[0])
              else reopenSidePanel()
            }}
            className="absolute right-3 top-3 z-10 inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-body-sm font-medium text-ink-secondary shadow-hairline hover:bg-surface-inset hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            {documentTurns[0]?.type === 'invoice' || sidePanelType === 'invoice' ? (
              <Receipt className="h-3.5 w-3.5 text-primary" />
            ) : (
              <FileText className="h-3.5 w-3.5 text-primary" />
            )}
            {documentTurns[0]?.type === 'invoice' || sidePanelType === 'invoice'
              ? '查看发票识别'
              : '查看合同审查'}
            <PanelRightOpen className="h-3.5 w-3.5 text-ink-tertiary" />
          </button>
        )}

        <StreamRenderer />
        <ChatWindow />
        <InputBox />
      </main>

      {rightPaneOpen && (
        <aside className="flex w-[440px] shrink-0 border-l border-line bg-surface animate-fade-in lg:w-[520px]">
          {sidePanelType === 'invoice' ? <InvoicePanel /> : <ContractPanel />}
        </aside>
      )}
    </div>
  )
}
