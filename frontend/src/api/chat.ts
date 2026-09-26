import { apiClient } from './client'
import type { StreamEvent, Session, Message } from '@/types'

// ================ 会话 ================

export const sessionApi = {
  list: () => apiClient.get<Session[]>('/sessions/').then((r) => r.data),
  create: () => apiClient.post<Session>('/sessions/').then((r) => r.data),
  get: (id: string) => apiClient.get<Session>(`/sessions/${id}`).then((r) => r.data),
  update: (id: string, data: { title?: string }) =>
    apiClient.patch<Session>(`/sessions/${id}`, data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/sessions/${id}`),
  messages: (id: string) =>
    apiClient.get<Message[]>(`/sessions/${id}/messages`).then((r) => r.data),
}

// ================ Chat 流式 ================

/**
 * 调用模型：客户端**先** `POST /files/upload` 拿到 `fileUrl/fileHash`，再把它们
 * 作为 JSON body 字段随 `message` 一起发到这里。chat_service 根据语义判断
 * 是否需要调用 OCR / 合同审查 / RAG 等工具。
 */
export async function* streamChat(
  sessionId: string,
  message: string,
  fileRef?: { id: string; file_url: string; file_hash: string; file_meta?: Record<string, unknown> },
): AsyncGenerator<StreamEvent> {
  const token = localStorage.getItem('access_token')
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      file_id: fileRef?.id,
      file_url: fileRef?.file_url,
      file_hash: fileRef?.file_hash,
      file_meta: fileRef?.file_meta,
    }),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No reader')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6))
          yield data as StreamEvent
        } catch {
          // 忽略解析错误
        }
      }
    }
  }
}