import { useEffect, useRef } from 'react'
import { useSessionStore } from '@/stores/sessionStore'
import { sessionApi } from '@/api/chat'

/**
 * 会话管理 hook
 * - 挂载时拉取当前用户的活跃会话
 * - 当前会话必须属于本次拉取的列表；换账号后丢弃上一账号的 sessionId
 * - 若列表为空，自动建一个新会话并切换过去
 * - 若列表非空且当前会话无效，自动选最近更新的会话
 *
 * StrictMode 兼容性说明：
 * - useRef 在同一次组件挂载内跨 cleanup→remount 是稳定的，因此 initRef 可以扛过
 *   React.StrictMode 的 mount→cleanup→mount 双调用，第二次 effect 直接返回；
 * - run-1 启动的 IIFE 不使用 cancelled 闭包标志，让它跑完（store 的写入对重复调用幂等）。
 *   "用户是否已经手动选了会话" 通过 useSessionStore.getState() 在 IIFE 内重新读取，
 *   这正是 useSSE.ts 中已经在用的读取最新状态的惯用法。
 */
export function useSessions() {
  const sessions = useSessionStore((s) => s.sessions)
  const setSessions = useSessionStore((s) => s.setSessions)
  const addSession = useSessionStore((s) => s.addSession)
  const setMessages = useSessionStore((s) => s.setMessages)
  const switchSession = useSessionStore((s) => s.switchSession)

  // 跨 StrictMode 双挂载保持："已经尝试过初始化"
  const initRef = useRef(false)

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    const ensureActiveSession = async () => {
      try {
        const list = await sessionApi.list()
        setSessions(list)

        // 仅当 currentSessionId 属于本次拉取的列表时才保留。
        // 换账号后若仍指向上一账号会话，会用新 token 去拉旧消息 → 401 → 被踢回登录页。
        const after = useSessionStore.getState()
        const currentStillValid =
          !!after.currentSessionId &&
          after.sessions.some((s) => s.id === after.currentSessionId)

        if (currentStillValid) return

        if (after.currentSessionId) switchSession(null)

        if (after.sessions.length > 0) {
          const sorted = [...after.sessions].sort(
            (a, b) =>
              new Date(b.updated_at || 0).getTime() -
              new Date(a.updated_at || 0).getTime(),
          )
          switchSession(sorted[0].id)
        } else {
          const session = await sessionApi.create()
          addSession(session)
          switchSession(session.id)
        }
      } catch {
        // 网络/服务异常：放开 ref，下次挂载时重试
        initRef.current = false
      }
    }

    void ensureActiveSession()
  }, [setSessions, switchSession, addSession])

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