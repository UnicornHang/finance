import { create } from 'zustand'
import type { Session, Message } from '@/types'

interface SessionState {
  sessions: Session[]
  currentSessionId: string | null
  messages: Record<string, Message[]>  // 按 sessionId 隔离

  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  removeSession: (id: string) => void
  updateSession: (id: string, data: Partial<Session>) => void

  switchSession: (id: string) => void
  setMessages: (sessionId: string, messages: Message[]) => void
  appendMessage: (sessionId: string, message: Message) => void
  clearMessages: (sessionId: string) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  currentSessionId: null,
  messages: {},

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({ sessions: [session, ...state.sessions] })),

  removeSession: (id) =>
    set((state) => {
      const { [id]: _, ...rest } = state.messages
      return {
        sessions: state.sessions.filter((s) => s.id !== id),
        messages: rest,
        currentSessionId:
          state.currentSessionId === id ? null : state.currentSessionId,
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

  clearMessages: (sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...rest } = state.messages
      return { messages: rest }
    }),
}))

// 选择器
export const useCurrentMessages = () => {
  const id = useSessionStore((s) => s.currentSessionId)
  const messages = useSessionStore((s) => (id ? s.messages[id] || [] : []))
  return messages
}