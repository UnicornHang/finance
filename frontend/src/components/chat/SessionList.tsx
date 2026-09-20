import { useState } from 'react'
import {
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Search,
  Trash2,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BrandLogo } from '@/components/ui/brand'
import { useSessionStore } from '@/stores/sessionStore'
import { useSessions } from '@/hooks/useSession'
import { cn, formatDate } from '@/lib/utils'

/**
 * 会话侧栏
 * - 280px 固定宽度
 * - 顶部品牌 + 搜索
 * - "新建会话" 突出
 * - 会话项 hover 显示操作菜单 (重命名/删除)
 */
export function SessionList() {
  const { sessions, createSession } = useSessions()
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const switchSession = useSessionStore((s) => s.switchSession)
  const removeSession = useSessionStore((s) => s.removeSession)
  const updateSession = useSessionStore((s) => s.updateSession)
  const clearMessages = useSessionStore((s) => s.clearMessages)

  const [query, setQuery] = useState('')
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)

  const handleNew = async () => {
    const session = await createSession()
    switchSession(session.id)
  }

  const handleSwitch = (id: string) => switchSession(id)

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setMenuOpenId(null)
    if (!confirm('确定删除此会话？此操作不可恢复')) return
    try {
      const { sessionApi } = await import('@/api/chat')
      await sessionApi.remove(id)
      removeSession(id)
      clearMessages(id)
    } catch {
      // ignore
    }
  }

  const handleRename = async (id: string, title: string | null) => {
    setMenuOpenId(null)
    const newTitle = prompt('重命名会话', title || '')
    if (newTitle && newTitle !== title) {
      try {
        const { sessionApi } = await import('@/api/chat')
        const updated = await sessionApi.update(id, { title: newTitle })
        updateSession(id, { title: updated.title })
      } catch {
        // ignore
      }
    }
  }

  const filtered = sessions.filter((s) =>
    (s.title || '新会话').toLowerCase().includes(query.toLowerCase()),
  )

  return (
    <aside className="flex w-[280px] shrink-0 flex-col bg-surface border-r border-line">
      {/* Brand */}
      <div className="px-5 pt-5 pb-3">
        <BrandLogo size={28} withWordmark />
      </div>

      {/* New session CTA */}
      <div className="px-3 pb-3">
        <Button onClick={handleNew} size="md" className="w-full">
          <MessageSquarePlus className="h-4 w-4" />
          新建会话
        </Button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary pointer-events-none" />
          <Input
            placeholder="搜索会话"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 pl-8 text-body-sm"
          />
        </div>
      </div>

      {/* Section label */}
      <div className="px-5 pt-2 pb-1.5">
        <span className="text-label-sm font-semibold uppercase tracking-wider text-ink-tertiary">
          近期会话
        </span>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {filtered.length === 0 ? (
          <div className="px-3 py-6 text-center text-body-sm text-ink-tertiary">
            {query ? '无匹配会话' : '暂无会话，开始第一次对话'}
          </div>
        ) : (
          <div className="space-y-0.5">
            {filtered.map((session) => {
              const isActive = currentSessionId === session.id
              const isMenuOpen = menuOpenId === session.id
              return (
                <div
                  key={session.id}
                  onClick={() => handleSwitch(session.id)}
                  className={cn(
                    'group relative flex cursor-pointer items-start gap-2 rounded-md px-3 py-2 transition-colors',
                    isActive
                      ? 'bg-primary-tint text-ink'
                      : 'hover:bg-surface-inset text-ink',
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
                          isActive ? 'bg-primary' : 'bg-ink-muted',
                        )}
                      />
                      <p
                        className={cn(
                          'truncate text-body-md font-semibold',
                          isActive && 'text-primary',
                        )}
                      >
                        {session.title || '新会话'}
                      </p>
                    </div>
                    <p className="ml-3 mt-0.5 truncate text-body-sm text-ink-tertiary">
                      {formatDate(session.updated_at)}
                    </p>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuOpenId(isMenuOpen ? null : session.id)
                    }}
                    aria-label="会话操作"
                    className={cn(
                      'flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-tertiary hover:bg-surface hover:text-ink',
                      (isMenuOpen || isActive) && 'opacity-100',
                      !isMenuOpen && !isActive && 'opacity-0 group-hover:opacity-100',
                    )}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>

                  {isMenuOpen && (
                    <div
                      className="absolute right-2 top-9 z-10 min-w-[140px] rounded-md border border-line-strong bg-surface shadow-raised"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        className="flex w-full items-center gap-2 px-3 py-2 text-body-md text-ink hover:bg-surface-inset"
                        onClick={() => handleRename(session.id, session.title)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        重命名
                      </button>
                      <button
                        className="flex w-full items-center gap-2 px-3 py-2 text-body-md text-danger hover:bg-danger-tint"
                        onClick={(e) => handleDelete(session.id, e)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        删除
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </aside>
  )
}