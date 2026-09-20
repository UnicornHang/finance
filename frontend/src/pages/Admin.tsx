import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { ArrowLeft, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import { BrandLogo } from '@/components/ui/brand'
import { Badge } from '@/components/ui/badge'
import { useAuthStore } from '@/stores/authStore'
import { Link } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '', label: '首页看板', icon: '⊞', description: '数据概览' },
  { to: 'invoices', label: '发票归档', icon: '🧾', description: '归档检索' },
  { to: 'contracts', label: '合同归档', icon: '📜', description: '风险审查' },
  { to: 'kb', label: '知识库', icon: '📚', description: 'RAG 文档' },
  { to: 'users', label: '用户管理', icon: '👥', description: '权限配置' },
  { to: 'llm', label: 'LLM 设置', icon: '⚙️', description: '模型路由' },
]

export function Admin() {
  const user = useAuthStore((s) => s.user)
  const location = useLocation()

  if (user?.role !== 'admin' && user?.role !== 'finance') {
    return <Navigate to="/chat" replace />
  }

  // 当前激活路径
  const currentPath = location.pathname.replace(/^\/admin\/?/, '') || ''
  const currentItem = NAV_ITEMS.find((item) => item.to === currentPath) || NAV_ITEMS[0]

  return (
    <div className="flex h-screen bg-canvas">
      {/* 左侧导航 */}
      <aside className="flex w-[240px] shrink-0 flex-col bg-surface border-r border-line">
        <div className="px-5 py-5">
          <BrandLogo size={28} withWordmark />
        </div>

        <div className="px-5 pb-2">
          <span className="text-label-sm font-semibold uppercase tracking-wider text-ink-tertiary">
            管理后台
          </span>
        </div>

        <nav className="flex-1 px-2 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === ''}
              className={({ isActive }) =>
                cn(
                  'group flex items-center gap-3 rounded-md px-3 py-2 text-body-md transition-colors',
                  isActive
                    ? 'bg-primary-tint text-primary'
                    : 'text-ink-secondary hover:bg-surface-inset hover:text-ink',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      'flex h-7 w-7 shrink-0 items-center justify-center rounded text-body-md',
                      isActive ? 'bg-primary text-white' : 'bg-canvas text-ink-tertiary',
                    )}
                  >
                    {item.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={cn('font-semibold', isActive && 'text-primary')}>
                      {item.label}
                    </p>
                    <p className="text-label-sm text-ink-tertiary truncate">
                      {item.description}
                    </p>
                  </div>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line-subtle p-3">
          <Link
            to="/chat"
            className="flex items-center gap-2 rounded-md px-3 py-2 text-body-sm text-ink-secondary hover:bg-surface-inset hover:text-ink"
          >
            <ArrowLeft className="h-4 w-4" />
            返回对话工作台
          </Link>
        </div>
      </aside>

      {/* 主区域 */}
      <main className="flex-1 overflow-y-auto">
        {/* 顶部面包屑 */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-8">
          <div className="flex items-center gap-2 text-body-md text-ink-tertiary">
            <span>管理后台</span>
            <ChevronRight className="h-3.5 w-3.5" />
            <span className="text-ink font-semibold">{currentItem.label}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="primary" dot>
              {user?.role === 'admin' ? '管理员视图' : '财务视图'}
            </Badge>
          </div>
        </header>

        <div className="px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}