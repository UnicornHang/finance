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

export async function* streamChat(
  sessionId: string,
  message: string,
  file?: File,
): AsyncGenerator<StreamEvent> {
  const formData = new FormData()
  formData.append('session_id', sessionId)
  formData.append('message', message)
  if (file) formData.append('file', file)

  const token = localStorage.getItem('access_token')
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
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