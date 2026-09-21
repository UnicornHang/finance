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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useSessionStore } from '@/stores/sessionStore'
import { useSessions } from '@/hooks/useSession'
import { cn, formatDate } from '@/lib/utils'

/**
 * 会话侧栏
 * - 280px 固定宽度
 * - 顶部品牌 + 搜索
 * - "新建会话" 突出
 * - 会话项 hover 显示 DropdownMenu (重命名/删除)
 */
export function SessionList() {
  const { sessions, createSession } = useSessions()
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const switchSession = useSessionStore((s) => s.switchSession)
  const removeSession = useSessionStore((s) => s.removeSession)
  const updateSession = useSessionStore((s) => s.updateSession)
  const clearMessages = useSessionStore((s) => s.clearMessages)

  const [query, setQuery] = useState('')
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleNew = async () => {
    const session = await createSession()
    switchSession(session.id)
  }

  const handleSwitch = (id: string) => switchSession(id)

  const openRename = (id: string, title: string | null) => {
    setRenameTarget({ id, title: title || '' })
    setRenameValue(title || '')
  }

  const submitRename = async () => {
    if (!renameTarget) return
    const newTitle = renameValue.trim()
    if (!newTitle || newTitle === renameTarget.title) {
      setRenameTarget(null)
      return
    }
    setBusy(true)
    try {
      const { sessionApi } = await import('@/api/chat')
      const updated = await sessionApi.update(renameTarget.id, { title: newTitle })
      updateSession(renameTarget.id, { title: updated.title })
    } catch {
      // ignore
    } finally {
      setBusy(false)
      setRenameTarget(null)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTargetId) return
    setBusy(true)
    try {
      const { sessionApi } = await import('@/api/chat')
      await sessionApi.remove(deleteTargetId)
      removeSession(deleteTargetId)
      clearMessages(deleteTargetId)
    } catch {
      // ignore
    } finally {
      setBusy(false)
      setDeleteTargetId(null)
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

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        onClick={(e) => e.stopPropagation()}
                        aria-label="会话操作"
                        className={cn(
                          'flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-tertiary hover:bg-surface hover:text-ink',
                          'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
                          isActive && 'opacity-100',
                          'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                        )}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="min-w-[140px]">
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation()
                          openRename(session.id, session.title)
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        重命名
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        variant="destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteTargetId(session.id)
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        删除
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 重命名 Dialog —— 替代原生 prompt() */}
      <Dialog
        open={!!renameTarget}
        onOpenChange={(o) => {
          if (!o && !busy) setRenameTarget(null)
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
            <DialogDescription>
              为当前会话设置一个新标题，最多 60 个字符。
            </DialogDescription>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            placeholder="请输入会话标题"
            maxLength={60}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy) submitRename()
            }}
          />
          <DialogFooter>
            <Button
              variant="secondary"
              size="md"
              onClick={() => setRenameTarget(null)}
              disabled={busy}
            >
              取消
            </Button>
            <Button
              size="md"
              onClick={submitRename}
              disabled={busy || !renameValue.trim()}
              className="text-white"
            >
              {busy ? '保存中...' : '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 AlertDialog —— 替代原生 confirm() */}
      <AlertDialog
        open={!!deleteTargetId}
        onOpenChange={(o) => {
          if (!o && !busy) setDeleteTargetId(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确定删除此会话？</AlertDialogTitle>
            <AlertDialogDescription>
              此操作不可恢复，会话消息将被永久删除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} disabled={busy}>
              {busy ? '删除中...' : '确定'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  )
}