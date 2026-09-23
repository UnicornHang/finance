import { useCallback } from 'react'

import { useUIStore } from '@/stores/uiStore'
import { useSessionStore } from '@/stores/sessionStore'
import { streamChat } from '@/api/chat'
import type { FileRef } from '@/api/file'
import type { Message } from '@/types'

/**
 * 临时消息 ID 生成器 — 用 crypto.randomUUID 避免 Date.now()
 * 在低精度时钟（Windows ~15ms）下产生碰撞，特别是连续快速发送时
 */
function tmpId(prefix: 'user' | 'assistant'): string {
  const uuid =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  return `tmp-${prefix}-${uuid}`
}

/**
 * Chat 流式发送 hook
 *
 * 注意：附件上传**已经在 InputBox 选文件那一瞬触发**（`POST /files/upload`），
 * 拿到 `FileRef` 后这里只负责把 `message + file_url + file_hash` 进 SSE 流。
 * chat_service 根据 LLM 语义判断调用 OCR / 合同审查 / RAG / 直接问答。
 */
export function useChat() {
  const openSidePanel = useUIStore((s) => s.openSidePanel)
  const setStreaming = useUIStore((s) => s.setStreaming)
  const appendMessage = useSessionStore((s) => s.appendMessage)
  const updateMessage = useSessionStore((s) => s.updateMessage)

  const send = useCallback(
    async (message: string, fileRef?: FileRef) => {
      const sessionId = useSessionStore.getState().currentSessionId
      if (!sessionId) return

      // 1. 追加用户消息
      const userMsg: Message = {
        id: tmpId('user'),
        role: 'user',
        content: message,
        tool_calls: null,
        created_at: new Date().toISOString(),
      }
      appendMessage(sessionId, userMsg)

      // 2. 准备 assistant 占位消息（id 固定，SSE 文本 chunk 会持续往这条上累加）
      const assistantMsg: Message = {
        id: tmpId('assistant'),
        role: 'assistant',
        content: '',
        tool_calls: null,
        created_at: new Date().toISOString(),
      }
      appendMessage(sessionId, assistantMsg)

      // 3. 用闭包局部变量累积内容（避免每次 chunk 都从 store 读，可读性 + 性能都更好）
      let accumulated = ''

      setStreaming(true)
      try {
        for await (const event of streamChat(sessionId, message, fileRef)) {
          if (event.type === 'text') {
            accumulated += event.content
            updateMessage(sessionId, assistantMsg.id, { content: accumulated })
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
    [appendMessage, updateMessage, openSidePanel, setStreaming],
  )

  return { send }
}