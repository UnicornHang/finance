import { useCallback, useState } from 'react'
import type { QueryObserverResult } from '@tanstack/react-query'
import { toast } from 'sonner'

import { readApiMessage } from '@/lib/apiError'

type PresignedResult = { url: string }

interface Options {
  /** 拉取/刷新「可预览」预签名 URL（用于复制链接） */
  refetch: () => Promise<QueryObserverResult<PresignedResult, Error>>
  /** 拉取带 attachment 的预签名 URL（用于真正下载） */
  fetchDownloadUrl: () => Promise<string>
  /** 上次成功拿到的缓存 URL，刷新失败时回退 */
  cachedUrl?: string
  isFetching: boolean
}

/** 通过隐藏 a 标签跳转，配合 Content-Disposition: attachment 触发下载 */
function navigateToDownload(url: string) {
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

/**
 * 详情弹窗原件操作：
 * - 获取下载链接 → 换临时预签名 URL 并复制到剪贴板（可预览）
 * - 下载原件 → 换强制下载链接并触发浏览器下载
 */
export function usePresignedFileActions({
  refetch,
  fetchDownloadUrl,
  cachedUrl,
  isFetching,
}: Options) {
  const [downloading, setDownloading] = useState(false)

  /** 优先刷新预签名，保证未过期；失败时回退缓存 */
  const ensurePreviewUrl = useCallback(async (): Promise<string> => {
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

  /** 复制临时下载链接（约 1 小时有效，打开后可预览） */
  const copyDownloadLink = useCallback(async () => {
    try {
      const url = await ensurePreviewUrl()
      await navigator.clipboard.writeText(url)
      toast.success('下载链接已复制，约 1 小时内有效')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : '复制下载链接失败')
    }
  }, [ensurePreviewUrl])

  /** 强制下载原件（非浏览器内联预览） */
  const downloadOriginal = useCallback(async () => {
    setDownloading(true)
    try {
      const url = await fetchDownloadUrl()
      navigateToDownload(url)
      toast.success('已开始下载原件')
    } catch (err: unknown) {
      toast.error(
        err instanceof Error
          ? err.message
          : readApiMessage(err) || '下载原件失败',
      )
    } finally {
      setDownloading(false)
    }
  }, [fetchDownloadUrl])

  return {
    copyDownloadLink,
    downloadOriginal,
    fileLoading: isFetching || downloading,
  }
}
