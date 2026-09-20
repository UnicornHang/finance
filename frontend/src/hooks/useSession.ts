import { useEffect, useRef } from 'react'
import { useSessionStore } from '@/stores/sessionStore'
import { sessionApi } from '@/api/chat'

/**
 * 会话管理 hook
 * - 挂载时拉取当前用户的活跃会话
 * - 若列表为空，自动建一个新会话并切换过去（改善首屏 UX）
 * - 通过 ref 防止重复触发
 */
export function useSessions() {
  const sessions = useSessionStore((s) => s.sessions)
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const setSessions = useSessionStore((s) => s.setSessions)
  const addSession = useSessionStore((s) => s.addSession)
  const setMessages = useSessionStore((s) => s.setMessages)
  const switchSession = useSessionStore((s) => s.switchSession)

  // 标记"已尝试自动建"，避免依赖变化时反复触发
  const autoCreatedRef = useRef(false)

  // 1. 首次加载：拉列表
  useEffect(() => {
    let cancelled = false
    sessionApi
      .list()
      .then((list) => {
        if (cancelled) return
        setSessions(list)
      })
      .catch(() => {
        // 静默失败：登录失效时会跳走，这里不必打扰
      })
    return () => {
      cancelled = true
    }
  }, [setSessions])

  // 2. 列表为空且无当前会话时：自动建一个
  useEffect(() => {
    if (autoCreatedRef.current) return
    if (sessions.length > 0) return
    if (currentSessionId) return

    autoCreatedRef.current = true
    let cancelled = false
    sessionApi
      .create()
      .then((session) => {
        if (cancelled) return
        addSession(session)
        switchSession(session.id)
      })
      .catch(() => {
        // 失败则放开 ref，允许下次重试
        autoCreatedRef.current = false
      })
    return () => {
      cancelled = true
    }
  }, [sessions.length, currentSessionId, addSession, switchSession])

  const createSession = async () => {
    const session = await sessionApi.create()
    addSession(session)
    return session
  }

  const loadMessages = async (sessionId: string) => {
    const msgs = await sessionApi.messages(sessionId)
    setMessages(sessionId, msgs)
  }

  return { sessions, createSession, loadMessages }
}
