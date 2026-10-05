import axios from 'axios'

import { resetClientState } from '@/lib/resetClientState'
import { useAuthStore } from '@/stores/authStore'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const apiClient = axios.create({
  baseURL,
  timeout: 30000,
})

/** 从请求头取出 Bearer token，用于判断是否为上一账号的过期请求。 */
function readRequestAccessToken(headers: unknown): string | null {
  if (!headers || typeof headers !== 'object') return null
  const rec = headers as { get?: (key: string) => unknown; Authorization?: unknown }
  const raw = typeof rec.get === 'function' ? rec.get('Authorization') : rec.Authorization
  if (typeof raw !== 'string' || !raw) return null
  return raw.replace(/^Bearer\s+/i, '')
}

// 请求拦截器：注入 Token（优先内存态，避免 persist 与散落 key 不一致）
apiClient.interceptors.request.use((config) => {
  const token =
    useAuthStore.getState().token || localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/**
 * 鉴权失败统一处理：清空凭证 + 跳转登录页。
 * - 清空 zustand auth state（含 token / user / refreshToken）
 *   同时 persist 中间件会自动移除 localStorage ['finance-auth']
 * - 兜底清理 localStorage 中散落的 access_token / refresh_token
 * - 硬跳转（window.location.href）重置整页 React 内存（含 react-query 缓存）
 */
export function handleAuthFailure() {
  try {
    resetClientState()
    useAuthStore.getState().logout()
  } catch {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// 响应拦截器：仅当前 token 的 401 视为会话失效
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = String(error.config?.url || '')
    const isLoginRequest = url.includes('/auth/login')
    if (status === 401 && !isLoginRequest) {
      const sent = readRequestAccessToken(error.config?.headers)
      const current = useAuthStore.getState().token
      // 上一账号退出后的在途 401，不能清掉刚登录的新 token
      if (sent && current && sent !== current) {
        return Promise.reject(error)
      }
      handleAuthFailure()
    }
    return Promise.reject(error)
  },
)
