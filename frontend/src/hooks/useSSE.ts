import { useCallback } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { useSessionStore } from '@/stores/sessionStore'
import { streamChat } from '@/api/chat'
import type { Message } from '@/types'

export function useChat() {
  const openSidePanel = useUIStore((s) => s.openSidePanel)
  const setStreaming = useUIStore((s) => s.setStreaming)
  const appendMessage = useSessionStore((s) => s.appendMessage)

  const send = useCallback(
    async (message: string, file?: File) => {
      const sessionId = useSessionStore.getState().currentSessionId
      if (!sessionId) return

      // 追加用户消息
      const userMsg: Message = {
        id: `tmp-${Date.now()}`,
        role: 'user',
        content: message,
        tool_calls: null,
        created_at: new Date().toISOString(),
      }
      appendMessage(sessionId, userMsg)

      // 准备 assistant 占位消息
      const assistantMsg: Message = {
        id: `tmp-${Date.now() + 1}`,
        role: 'assistant',
        content: '',
        tool_calls: null,
        created_at: new Date().toISOString(),
      }
      appendMessage(sessionId, assistantMsg)

      setStreaming(true)
      try {
        for await (const event of streamChat(sessionId, message, file)) {
          if (event.type === 'text') {
            appendMessage(sessionId, {
              ...assistantMsg,
              content: (assistantMsg.content || '') + event.content,
            })
          } else if (event.type === 'sidepanel') {
            openSidePanel(event.payload.type, event.payload.data)
          } else if (event.type === 'done') {
            break
          } else if (event.type === 'error') {
            throw new Error(event.message)
          }
        }
      } finally {
        setStreaming(false)
      }
    },
    [appendMessage, openSidePanel, setStreaming],
  )

  return { send }
}