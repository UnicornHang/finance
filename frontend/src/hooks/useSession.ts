import { useEffect, useRef } from 'react'
import { useSessionStore } from '@/stores/sessionStore'
import { sessionApi } from '@/api/chat'

/**
 * 会话管理 hook
 * - 挂载时拉取当前用户的活跃会话
 * - 若列表为空，自动建一个新会话并切换过去
 * - 若列表非空且无当前会话，自动选最近更新的会话
 * - 保留用户在 list 加载期间手动创建的会话（不被 setSessions 覆盖丢失）
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

        // 捕获 setSessions 之前的状态：用户可能在此期间已经手动创建/切换了会话
        const before = useSessionStore.getState()

        setSessions(list)

        // 1) 若用户在 list 加载期间手动创建了会话（currentSessionId 指向它但服务端
        //    list 里没有），把它重新插到最前面 —— 避免被 setSessions 覆盖丢失
        if (
          before.currentSessionId &&
          !list.some((s) => s.id === before.currentSessionId)
        ) {
          const manual = before.sessions.find(
            (s) => s.id === before.currentSessionId,
          )
          if (manual) {
            setSessions([manual, ...list])
          }
        }

        // 2) 仍未选中会话：根据列表是否为空决定行为
        const after = useSessionStore.getState()
        if (after.currentSessionId) return

        if (after.sessions.length > 0) {
          // 列表非空：选最近更新的会话（updated_at 倒序）
          const sorted = [...after.sessions].sort(
            (a, b) =>
              new Date(b.updated_at || 0).getTime() -
              new Date(a.updated_at || 0).getTime(),
          )
          switchSession(sorted[0].id)
        } else {
          // 列表为空：建一个新会话
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