import {
  NavLink,
  Navigate,
  Outlet,
  Link,
} from 'react-router-dom'
import {
  LayoutDashboard,
  Receipt,
  FileText,
  BookOpen,
  Users,
  Cpu,
  ShieldCheck,
  Search,
  Bell,
  HelpCircle,
  Settings,
  MessageSquare,
  LogOut,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { BrandLogo } from '@/components/ui/brand'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'

const NAV_ITEMS = [
  { to: '', label: '数据概览', icon: LayoutDashboard },
  { to: 'invoices', label: '发票归档', icon: Receipt },
  { to: 'contracts', label: '合同归档', icon: FileText },
  { to: 'kb', label: '知识库', icon: BookOpen },
  { to: 'users', label: '用户管理', icon: Users },
  { to: 'llm', label: 'LLM 设置', icon: Cpu },
]

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

export function Admin() {
  const user = useAuthStore((s) => s.user)
  const { logout } = useAuth()

  if (user?.role !== 'admin' && user?.role !== 'finance') {
    return <Navigate to="/chat" replace />
  }

  const role = user?.role || 'employee'

  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      {/* ============ 顶部头部 (Figma: 1:744) ============ */}
      <header className="flex h-16 shrink-0 items-center gap-6 border-b border-line bg-surface px-6">
        {/* 左：品牌 */}
        <div className="flex shrink-0 items-center">
          <BrandLogo size={32} withWordmark />
        </div>

        {/* 中：Admin 内部分页快速切换 */}
        <nav className="flex flex-1 items-center justify-center gap-1 overflow-hidden">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === ''}
              className={({ isActive }) =>
                cn(
                  'relative flex shrink-0 items-center gap-2 rounded-md px-3 py-1.5',
                  'text-body-md font-medium transition-colors',
                  isActive
                    ? 'bg-primary-tint text-primary'
                    : 'text-ink-secondary hover:bg-surface-inset hover:text-ink',
                )
              }
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="whitespace-nowrap">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* 右：搜索 + 通知 + 帮助 + 用户 */}
        <div className="flex shrink-0 items-center gap-2">
          {/* 搜索框 */}
          {/* <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-tertiary" />
            <Input
              type="text"
              placeholder="搜索菜单 / 用户 / 文档…"
              className="h-8 w-56 pl-8 pr-3 bg-canvas"
            />
          </div> */}

          {/* 通知 */}
          <Button variant="ghost" size="icon" aria-label="通知">
            <Bell className="h-4 w-4" />
          </Button>

          {/* 帮助 */}
          <Button variant="ghost" size="icon" aria-label="帮助">
            <HelpCircle className="h-4 w-4" />
          </Button>

          {/* 用户下拉 */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className={cn(
                  'flex items-center gap-2 rounded-md px-2 py-1',
                  'hover:bg-surface-inset transition-colors',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                )}
              >
                <div
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-full',
                    'bg-primary-tint text-primary text-body-md font-semibold',
                  )}
                >
                  {user?.name?.[0] || 'U'}
                </div>
                <div className="hidden flex-col items-start leading-tight md:flex">
                  <span className="text-body-sm font-semibold text-ink">
                    {user?.name || '未登录'}
                  </span>
                  <span className="text-label-sm text-ink-tertiary">
                    {ROLE_LABEL[role]}
                  </span>
                </div>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[220px]">
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
              <DropdownMenuItem asChild>
                <Link to="/chat">
                  <MessageSquare className="h-4 w-4 text-ink-tertiary" />
                  返回对话工作台
                </Link>
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

      {/* ============ 主体：侧边栏 + 内容 ============ */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧 Aside (Figma: 1:4) */}
        <aside
          className={cn(
            'flex w-[256px] shrink-0 flex-col bg-surface border-r border-line',
          )}
        >
          <nav className="flex-1 space-y-0.5 overflow-y-auto px-2">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === ''}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-md px-3 py-2',
                    'text-body-md font-medium transition-colors',
                    isActive
                      ? 'bg-primary-tint text-primary'
                      : 'text-ink-secondary hover:bg-surface-inset hover:text-ink',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <item.icon
                      className={cn(
                        'h-4 w-4 shrink-0',
                        isActive ? 'text-primary' : 'text-ink-tertiary',
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          {/* Agent 状态卡 (Figma: 1:34) */}
          <div className="border-t border-line-subtle p-3">
            <div
              className={cn(
                'rounded-md border border-primary-border bg-primary-tint p-3',
              )}
            >
              <div className="flex items-center justify-center gap-2">
                <ShieldCheck className="h-4 w-4 shrink-0 text-primary" />
                <span className="text-body-sm font-semibold text-primary">
                  系统策略 / 权限合规
                </span>
              </div>
            </div>
          </div>
        </aside>

        {/* 主区域 */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-8 py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
