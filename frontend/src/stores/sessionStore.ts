import { create } from 'zustand'
import type { Session, Message } from '@/types'

/** 置顶 ID 持久化 key —— 用 localStorage 而非 DB（后端 Session 模型暂无 pinned 字段） */
const PINNED_STORAGE_KEY = 'chat.pinnedSessionIds.v1'

function loadPinnedIds(): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(PINNED_STORAGE_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr.filter((v) => typeof v === 'string') : []
  } catch {
    return []
  }
}

function savePinnedIds(ids: string[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // ignore quota / disabled storage
  }
}

interface SessionState {
  sessions: Session[]
  currentSessionId: string | null
  messages: Record<string, Message[]>  // 按 sessionId 隔离

  /** 批量选择模式（DeepSeek 风多选） */
  selectionMode: boolean
  selectedIds: string[]
  /** 置顶会话 ID 列表（按置顶时间倒序，最新的置顶在最前） */
  pinnedIds: string[]

  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  removeSession: (id: string) => void
  updateSession: (id: string, data: Partial<Session>) => void

  switchSession: (id: string) => void
  setMessages: (sessionId: string, messages: Message[]) => void
  appendMessage: (sessionId: string, message: Message) => void
  updateMessage: (
    sessionId: string,
    messageId: string,
    patch: Partial<Message>,
  ) => void
  clearMessages: (sessionId: string) => void

  enterSelectionMode: (initialId?: string) => void
  exitSelectionMode: () => void
  toggleSelected: (id: string) => void
  clearSelection: () => void

  togglePinned: (id: string) => void
  isPinned: (id: string) => boolean
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: {},
  selectionMode: false,
  selectedIds: [],
  pinnedIds: loadPinnedIds(),

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({
      sessions: [session, ...state.sessions],
      // 同时初始化 messages 槽位，避免 useCurrentMessages 读到 undefined
      messages: state.messages[session.id]
        ? state.messages
        : { ...state.messages, [session.id]: [] },
    })),

  removeSession: (id) =>
    set((state) => {
      const { [id]: _, ...rest } = state.messages
      return {
        sessions: state.sessions.filter((s) => s.id !== id),
        messages: rest,
        currentSessionId:
          state.currentSessionId === id ? null : state.currentSessionId,
        selectedIds: state.selectedIds.filter((sid) => sid !== id),
        pinnedIds: state.pinnedIds.filter((pid) => pid !== id),
      }
    }),

  updateSession: (id, data) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, ...data } : s)),
    })),

  switchSession: (id) => set({ currentSessionId: id }),

  setMessages: (sessionId, messages) =>
    set((state) => ({ messages: { ...state.messages, [sessionId]: messages } })),

  appendMessage: (sessionId, message) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [sessionId]: [...(state.messages[sessionId] || []), message],
      },
    })),

  updateMessage: (sessionId, messageId, patch) =>
    set((state) => {
      const list = state.messages[sessionId]
      if (!list) return state
      return {
        messages: {
          ...state.messages,
          [sessionId]: list.map((m) =>
            m.id === messageId ? { ...m, ...patch } : m,
          ),
        },
      }
    }),

  clearMessages: (sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...rest } = state.messages
      return { messages: rest }
    }),

  // ===== 多选模式 =====

  enterSelectionMode: (initialId) =>
    set((state) => ({
      selectionMode: true,
      selectedIds: initialId ? [initialId] : state.selectedIds,
    })),

  exitSelectionMode: () => set({ selectionMode: false, selectedIds: [] }),

  toggleSelected: (id) =>
    set((state) => ({
      selectedIds: state.selectedIds.includes(id)
        ? state.selectedIds.filter((sid) => sid !== id)
        : [...state.selectedIds, id],
    })),

  clearSelection: () => set({ selectedIds: [] }),

  // ===== 置顶 =====

  togglePinned: (id) => {
    const next = get().pinnedIds.includes(id)
      ? get().pinnedIds.filter((pid) => pid !== id)
      : [id, ...get().pinnedIds.filter((pid) => pid !== id)]
    savePinnedIds(next)
    set({ pinnedIds: next })
  },

  isPinned: (id) => get().pinnedIds.includes(id),
}))

// 选择器 — 必须返回稳定引用，否则 zustand useSyncExternalStore 会无限循环
const EMPTY_MESSAGES: ReadonlyArray<never> = Object.freeze([]) as ReadonlyArray<never>

export const useCurrentMessages = () => {
  // 把 id 放进 selector，避免闭包 stale；同时不构造新数组
  // 注意：新建会话时 store.messages[id] 尚未初始化，必须兜底 undefined
  return useSessionStore((s) => {
    if (!s.currentSessionId) return EMPTY_MESSAGES
    return s.messages[s.currentSessionId] ?? EMPTY_MESSAGES
  })
}