import {
  QueryCache,
  QueryClient,
  type QueryClientConfig,
} from '@tanstack/react-query'
import { toast } from 'sonner'

type ApiError = {
  response?: {
    status: number
    data?: { detail?: string; message?: string; error?: string }
  }
  code?: string
  message?: string
}

function showErrorToast(error: unknown) {
  const err = error as ApiError
  const status = err?.response?.status
  const detail =
    err?.response?.data?.detail ||
    err?.response?.data?.message ||
    err?.response?.data?.error

  // 鉴权类：交由 axios 拦截器统一跳转，这里不再提示
  if (status === 401 || status === 403) return

  if (status === 404) {
    toast.error(detail || '资源不存在（404）')
    return
  }
  if (status === 408 || err?.code === 'ECONNABORTED') {
    toast.error('请求超时，请稍后重试')
    return
  }
  if (status && status >= 500) {
    toast.error(detail || `服务器异常（${status}），请稍后重试`)
    return
  }
  if (status && status >= 400) {
    toast.error(detail || `请求失败（${status}）`)
    return
  }
  // 无 status：网络层错误
  toast.error(detail || err?.message || '网络异常，请检查连接')
}

const baseConfig: QueryClientConfig = {
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error: unknown) => {
        const err = error as ApiError
        const status = err?.response?.status
        // 4xx（除 408）一律不重试；5xx 重试 1 次
        if (
          status === 401 ||
          status === 403 ||
          status === 404 ||
          status === 408
        ) {
          return false
        }
        if (status && status >= 500) return failureCount < 1
        return failureCount < 1
      },
    },
  },
  // 全局 query 错误显示：mutations 由组件内 onError 自行处理
  // （避免与现有的 mutation toast 重复提示）
  queryCache: new QueryCache({
    onError: (error) => showErrorToast(error),
  }),
}

export const queryClient = new QueryClient(baseConfig)
