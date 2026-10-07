import { useCallback } from 'react'
import type { QueryObserverResult } from '@tanstack/react-query'
import { toast } from 'sonner'

import { readApiMessage } from '@/lib/apiError'

type PresignedResult = { url: string }

interface Options {
  /** 拉取/刷新预签名 URL */
  refetch: () => Promise<QueryObserverResult<PresignedResult, Error>>
  /** 上次成功拿到的缓存 URL，刷新失败时回退 */
  cachedUrl?: string
  isFetching: boolean
}

/**
 * 详情弹窗原件操作：
 * - 获取下载链接 → 换临时预签名 URL 并复制到剪贴板
 * - 下载原件 → 换链后在新窗口打开
 */
export function usePresignedFileActions({
  refetch,
  cachedUrl,
  isFetching,
}: Options) {
  /** 优先刷新预签名，保证未过期；失败时回退缓存 */
  const ensureUrl = useCallback(async (): Promise<string> => {
    const result = await refetch()
    const url = result.data?.url || cachedUrl
    if (!url) {
      const msg = result.error
        ? readApiMessage(result.error) || '获取下载链接失败'
        : '获取下载链接失败'
      throw new Error(msg)
    }
    return url
  }, [refetch, cachedUrl])

  /** 复制临时下载链接（约 1 小时有效） */
  const copyDownloadLink = useCallback(async () => {
    try {
      const url = await ensureUrl()
      await navigator.clipboard.writeText(url)
      toast.success('下载链接已复制，约 1 小时内有效')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : '复制下载链接失败')
    }
  }, [ensureUrl])

  /** 打开原件下载/预览 */
  const downloadOriginal = useCallback(async () => {
    try {
      const url = await ensureUrl()
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : '下载原件失败')
    }
  }, [ensureUrl])

  return {
    copyDownloadLink,
    downloadOriginal,
    fileLoading: isFetching,
  }
}
