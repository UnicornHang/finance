import { apiClient } from './client'
import type {
  User,
  LLMConfig,
  LLMProvider,
  LLMScene,
  LLMTestResult,
  KbDocument,
} from '@/types'

export const userApi = {
  list: () => apiClient.get<User[]>('/users/').then((r) => r.data),
  create: (data: Partial<User> & { password: string }) =>
    apiClient.post<User>('/users/', data).then((r) => r.data),
  update: (id: string, data: Partial<User>) =>
    apiClient.patch<User>(`/users/${id}`, data).then((r) => r.data),
  resetPassword: (id: string) =>
    apiClient.post(`/users/${id}/reset-password`).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/users/${id}`),
}

export interface LlmConfigPayload {
  provider: string
  model: string
  api_key?: string
  base_url?: string | null
  temperature?: number
  max_tokens?: number
  timeout_seconds?: number
  enabled?: boolean
  system_prompt?: string | null
}

export const llmApi = {
  listProviders: () =>
    apiClient.get<LLMProvider[]>('/llm/providers').then((r) => r.data),
  listScenes: () =>
    apiClient.get<LLMScene[]>('/llm/scenes').then((r) => r.data),
  listConfigs: () =>
    apiClient.get<LLMConfig[]>('/llm/configs').then((r) => r.data),
  getConfig: (scene: string) =>
    apiClient.get<LLMConfig>(`/llm/configs/${scene}`).then((r) => r.data),
  upsertConfig: (scene: string, payload: LlmConfigPayload) =>
    apiClient.put<LLMConfig>(`/llm/configs/${scene}`, payload).then((r) => r.data),
  deleteConfig: (scene: string) =>
    apiClient.delete(`/llm/configs/${scene}`).then((r) => r.data),
  testSavedConfig: (scene: string) =>
    apiClient.post<LLMTestResult>(`/llm/configs/${scene}/test`).then((r) => r.data),
  testPayload: (payload: LlmConfigPayload) =>
    apiClient.post<LLMTestResult>('/llm/test', payload).then((r) => r.data),
}

export const kbApi = {
  list: () => apiClient.get<KbDocument[]>('/kb/documents').then((r) => r.data),
  upload: (formData: FormData) =>
    apiClient.post<KbDocument>('/kb/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/kb/documents/${id}`),
  reindex: (id: string) =>
    apiClient.post(`/kb/documents/${id}/reindex`).then((r) => r.data),
  testRetrieve: (question: string) =>
    apiClient.post('/kb/test-retrieve', { question }).then((r) => r.data),
}