import { ChevronDown, ExternalLink, LogOut, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'

import { SessionList } from '@/components/chat/SessionList'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBox } from '@/components/chat/InputBox'
import { StreamRenderer } from '@/components/chat/StreamRenderer'
import { InvoicePanel } from '@/components/sidepanel/InvoicePanel'
import { ContractPanel } from '@/components/sidepanel/ContractPanel'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'

const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  finance: '财务',
  employee: '员工',
}

const ROLE_TONE: Record<string, 'primary' | 'success' | 'neutral'> = {
  admin: 'primary',
  finance: 'success',
  employee: 'neutral',
}

export function Chat() {
  const user = useAuthStore((s) => s.user)
  const { logout } = useAuth()

  const role = user?.role || 'employee'

  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-6">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-title-lg font-semibold text-ink">
            对话工作台
          </span>
          <Badge tone="neutral">Pristine Crisp Fintech</Badge>
        </div>

        <div className="relative flex items-center gap-2">
          {user?.role === 'admin' && (
            <Link to="/admin" target="_blank">
              <Button variant="secondary" size="sm">
                <ExternalLink className="h-3.5 w-3.5" />
                后台
              </Button>
            </Link>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-body-md text-ink hover:bg-surface-inset focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              >
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-tint text-primary text-label-md font-semibold">
                  {user?.name?.[0] || 'U'}
                </div>
                <div className="hidden sm:flex flex-col items-start leading-tight">
                  <span className="text-body-sm font-semibold text-ink">
                    {user?.name || '未登录'}
                  </span>
                  <span className="text-label-sm text-ink-tertiary">
                    {ROLE_LABEL[role]}
                  </span>
                </div>
                <ChevronDown className="h-3.5 w-3.5 text-ink-tertiary" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[200px]">
              <div className="px-2 py-2">
                <p className="text-body-md font-semibold text-ink">
                  {user?.name}
                </p>
                <p className="mt-0.5 text-label-sm text-ink-tertiary">
                  {user?.account}
                </p>
                <Badge tone={ROLE_TONE[role]} className="mt-2">
                  {ROLE_LABEL[role]}
                </Badge>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem>
                <Settings className="h-4 w-4 text-ink-tertiary" />
                账户设置
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onClick={logout}>
                <LogOut className="h-4 w-4" />
                登出
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Workspace */}
      <div className="flex flex-1 overflow-hidden">
        <SessionList />

        <main className="flex flex-1 flex-col min-w-0 bg-canvas">
          <StreamRenderer />
          <ChatWindow />
          <InputBox />
        </main>
      </div>

      <InvoicePanel />
      <ContractPanel />
    </div>
  )
}