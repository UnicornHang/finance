import axios from 'axios'

import { useAuthStore } from '@/stores/authStore'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const apiClient = axios.create({
  baseURL,
  timeout: 30000,
})

// 请求拦截器：注入 Token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
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
    useAuthStore.getState().logout()
  } catch {
    // 兜底
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// 响应拦截器：401 / 403 视为鉴权失败
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401 || status === 403) {
      handleAuthFailure()
    }
    return Promise.reject(error)
  },
)
