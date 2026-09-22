import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ExternalLink,
  LogOut,
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  X,
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
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useSessionStore } from '@/stores/sessionStore'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'
import { useSessions } from '@/hooks/useSession'
import { cn, getDateBucket } from '@/lib/utils'
import type { Session } from '@/types'

/**
 * DeepSeek 风格会话侧栏
 *
 * 布局（顶到底）：
 * 1. 顶部品牌行：Logo + 搜索/新建图标快捷键
 * 2. 「+ 开启新对话」全宽按钮
 * 3. 搜索输入
 * 4. 按时间桶分组的会话列表（今天 / 7天内 / 30天内 / YYYY-MM）
 * 5. 用户底部信息条：头像 + 账号 + 下拉菜单（后台 / 账户设置 / 登出）
 */
export function SessionList() {
  const { sessions, createSession } = useSessions()
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const switchSession = useSessionStore((s) => s.switchSession)
  const removeSession = useSessionStore((s) => s.removeSession)
  const updateSession = useSessionStore((s) => s.updateSession)
  const clearMessages = useSessionStore((s) => s.clearMessages)

  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleNew = async () => {
    const session = await createSession()
    switchSession(session.id)
  }

  const handleSwitch = (id: string) => switchSession(id)

  const openSearch = () => {
    setSearchOpen(true)
    // 等下一帧 Input 挂载后再聚焦
    requestAnimationFrame(() => searchRef.current?.focus())
  }
  const closeSearch = () => {
    setSearchOpen(false)
    setQuery('')
  }

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

  // 按时间桶分组（保持稳定顺序：今天 → 7天内 → 30天内 → older 月份倒序）
  const grouped = useMemo(() => groupByBucket(filtered), [filtered])

  return (
    <aside className="flex w-[260px] shrink-0 flex-col bg-surface border-r border-line">
      {/* 1. 顶部品牌行 —— 搜索展开时整体替换为搜索输入 */}
      {searchOpen ? (
        <div className="flex items-center gap-2 px-3 pt-3 pb-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary pointer-events-none" />
            <Input
              ref={searchRef}
              placeholder="搜索会话"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') closeSearch()
              }}
              className="h-8 pl-8 text-body-sm"
            />
          </div>
          <button
            type="button"
            aria-label="关闭搜索"
            title="关闭搜索"
            onClick={closeSearch}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-tertiary hover:bg-surface-inset hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
          <BrandLogo size={26} withWordmark />
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              aria-label="搜索会话"
              title="搜索会话"
              onClick={openSearch}
              className="flex h-8 w-8 items-center justify-center rounded-md text-ink-tertiary hover:bg-surface-inset hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <Search className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="新建会话"
              title="新建会话"
              onClick={handleNew}
              className="flex h-8 w-8 items-center justify-center rounded-md text-ink-tertiary hover:bg-surface-inset hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* 2. 「开启新对话」按钮（DeepSeek 风） */}
      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={handleNew}
          className="group flex w-full items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-2 text-body-md text-ink transition-colors hover:border-line-strong hover:bg-surface-inset focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        >
          <MessageSquarePlus className="h-4 w-4 text-ink-secondary transition-transform group-hover:scale-105" />
          <span className="font-medium">开启新对话</span>
        </button>
      </div>

      {/* 4. 按时间桶分组的会话列表 */}
      <div className="flex-1 overflow-y-auto pb-2">
        {filtered.length === 0 ? (
          <div className="px-4 py-8 text-center text-body-sm text-ink-tertiary">
            {query ? '无匹配会话' : '暂无会话，开启第一次对话'}
          </div>
        ) : (
          <div className="space-y-3">
            {grouped.map((group) => (
              <div key={group.key}>
                <div className="px-4 pb-1">
                  <span className="text-label-sm font-semibold uppercase tracking-wider text-ink-tertiary">
                    {group.label}
                  </span>
                </div>
                <div className="space-y-0.5 px-2">
                  {group.sessions.map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      active={currentSessionId === session.id}
                      onSelect={() => handleSwitch(session.id)}
                      onRename={() => openRename(session.id, session.title)}
                      onDelete={() => setDeleteTargetId(session.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 5. 用户底部信息条 */}
      <UserFooter />

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

/* ============================================================ */

function SessionRow({
  session,
  active,
  onSelect,
  onRename,
  onDelete,
}: {
  session: Session
  active: boolean
  onSelect: () => void
  onRename: () => void
  onDelete: () => void
}) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        'group relative flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors',
        active
          ? 'bg-primary-tint text-ink'
          : 'hover:bg-surface-inset text-ink',
      )}
    >
      <span
        className={cn(
          'min-w-0 flex-1 truncate text-body-sm',
          active && 'font-semibold text-primary',
        )}
      >
        {session.title || '新会话'}
      </span>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            onClick={(e) => e.stopPropagation()}
            aria-label="会话操作"
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded text-ink-tertiary hover:bg-surface hover:text-ink',
              'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
              active && 'opacity-100',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
            )}
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[140px]">
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onRename()
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
            重命名
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            删除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

/* ============================================================ */

const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  finance: '财务',
  employee: '员工',
}

/** 用户底部信息条 — DeepSeek 风：头像 + 账号 + 「...」下拉菜单 */
function UserFooter() {
  const user = useAuthStore((s) => s.user)
  const { logout } = useAuth()

  if (!user) return null

  const maskedAccount = maskAccount(user.account)

  return (
    <div className="border-t border-line-subtle p-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-surface-inset focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-tint text-primary text-label-md font-semibold">
              {user.name?.[0] || 'U'}
            </div>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-body-sm font-semibold text-ink">
                {user.name || '未登录'}
              </p>
              <p className="truncate text-label-sm text-ink-tertiary">
                {maskedAccount}
              </p>
            </div>
            <MoreHorizontal className="h-4 w-4 shrink-0 text-ink-tertiary group-hover:text-ink" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="top" className="min-w-[220px]">
          <DropdownMenuLabel className="font-normal">
            <div className="space-y-1">
              <p className="text-body-md font-semibold text-ink">{user.name}</p>
              <p className="text-label-sm text-ink-tertiary">{user.account}</p>
              <p className="text-label-sm text-ink-tertiary">
                {ROLE_LABEL[user.role] || user.role}
              </p>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {user.role === 'admin' && (
            <DropdownMenuItem asChild>
              <Link to="/admin" target="_blank">
                <ExternalLink className="h-3.5 w-3.5" />
                后台管理
              </Link>
            </DropdownMenuItem>
          )}
          <DropdownMenuItem disabled>
            <Settings className="h-3.5 w-3.5" />
            账户设置
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onClick={logout}>
            <LogOut className="h-3.5 w-3.5" />
            登出
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

/* ============================================================ */

/** 账号脱敏：15612345678 → 156****5678；长度 < 7 时整段打码 */
function maskAccount(account: string | undefined | null): string {
  if (!account) return '—'
  if (account.length <= 6) return '****'
  return `${account.slice(0, 3)}****${account.slice(-4)}`
}

/* ============================================================ */

type Group = { key: string; label: string; sessions: Session[] }

/** 按 DeepSeek 风格分组：
 *  - 顺序：今天 → 7天内 → 30天内 → older 月份倒序
 *  - 同月份内按 updated_at 倒序
 */
function groupByBucket(sessions: Session[]): Group[] {
  const today: Session[] = []
  const seven: Session[] = []
  const thirty: Session[] = []
  const olderMap = new Map<string, { label: string; list: Session[] }>()

  for (const s of sessions) {
    const b = getDateBucket(s.updated_at)
    if (b.bucket === 'today') today.push(s)
    else if (b.bucket === '7days') seven.push(s)
    else if (b.bucket === '30days') thirty.push(s)
    else {
      const existing = olderMap.get(b.monthKey)
      if (existing) existing.list.push(s)
      else olderMap.set(b.monthKey, { label: b.label, list: [s] })
    }
  }

  const sortDesc = (a: Session, b: Session) =>
    new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime()

  today.sort(sortDesc)
  seven.sort(sortDesc)
  thirty.sort(sortDesc)

  const older = Array.from(olderMap.entries())
    .sort(([a], [b]) => (a < b ? 1 : -1)) // 月份倒序
    .map(([key, { label, list }]) => {
      list.sort(sortDesc)
      return { key, label, sessions: list }
    })

  const result: Group[] = []
  if (today.length) result.push({ key: 'today', label: '今天', sessions: today })
  if (seven.length) result.push({ key: '7days', label: '7天内', sessions: seven })
  if (thirty.length) result.push({ key: '30days', label: '30天内', sessions: thirty })
  result.push(...older)
  return result
}