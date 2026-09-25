import { useEffect, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Paperclip, Send, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useSessionStore } from '@/stores/sessionStore'
import { useUIStore } from '@/stores/uiStore'
import { useChat } from '@/hooks/useSSE'
import { fileApi, type FileRef } from '@/api/file'
import { cn } from '@/lib/utils'

type UploadStatus = 'idle' | 'uploading' | 'uploaded' | 'error'

/**
 * 输入框
 * - 多行自适应
 * - 文件 chip 在选择后浮于上方
 * - **选完即传**：选择文件后立刻调 `POST /files/upload`（不阻塞文本输入）；
 *   发送时只携带 file_url / file_hash 进 chat_stream
 * - 用户中途点 × 或重新选文件：abort 进行中的上传
 */
export function InputBox() {
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [fileRef, setFileRef] = useState<FileRef | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const fileRefInput = useRef<HTMLInputElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const fileMetaRef = useRef<{ name: string; size: number } | null>(null)

  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const streaming = useUIStore((s) => s.streaming)
  const { send } = useChat()

  const adjustHeight = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }

  // 选中新文件：abort 旧上传，立即开始新上传
  const startUpload = (next: File) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    fileMetaRef.current = { name: next.name, size: next.size }

    setFile(next)
    setFileRef(null)
    setUploadStatus('uploading')
    setUploadError(null)

    fileApi
      .upload(next, ctrl.signal)
      .then((r) => {
        // 用户可能在 await 期间已经换了文件 — 用 fileMetaRef 校验是否还是同一文件
        if (fileMetaRef.current?.name !== next.name || fileMetaRef.current?.size !== next.size) {
          return
        }
        setFileRef({
          file_url: r.file_url,
          file_hash: r.file_hash,
          file_meta: {
            original_filename: r.original_filename,
            content_type: r.content_type,
            size: r.size,
          },
        })
        setUploadStatus('uploaded')
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        // 完整打 console：包含 axios 的 config / response / request —— 排查 net::ERR_* 时最有用
        // eslint-disable-next-line no-console
        console.error('[InputBox] file upload failed:', err, {
          url: '/files/upload',
          fileName: next.name,
          fileSize: next.size,
        })
        const detail =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : null
        const message =
          err && typeof err === 'object' && 'message' in err && typeof (err as { message?: unknown }).message === 'string'
            ? (err as { message: string }).message
            : null
        const code =
          err && typeof err === 'object' && 'code' in err && typeof (err as { code?: unknown }).code === 'string'
            ? (err as { code: string }).code
            : null
        setUploadStatus('error')
        setUploadError(detail || message || code || '上传失败，请重试')
      })
  }

  // 移掉附件：abort + 清空所有状态
  const handleRemoveFile = () => {
    abortRef.current?.abort()
    abortRef.current = null
    fileMetaRef.current = null
    setFile(null)
    setFileRef(null)
    setUploadStatus('idle')
    setUploadError(null)
    if (fileRefInput.current) fileRefInput.current.value = ''
  }

  // 卸载时清理未完成的上传
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const handleSend = async () => {
    const hasText = !!text.trim()
    const hasFile = !!file && uploadStatus === 'uploaded' && !!fileRef
    if ((!hasText && !hasFile) || !currentSessionId || streaming) return
    if (file && uploadStatus !== 'uploaded') {
      // 上传未完成或失败，不发送（不让 chat_stream 拿到一个空的 file_url）
      return
    }
    const msg = text
    const ref = fileRef
    setText('')
    handleRemoveFile()
    if (taRef.current) taRef.current.style.height = 'auto'
    await send(msg, ref ?? undefined)
  }

  // 允许纯文字或「仅附件」发送（后端也支持 file-only）
  const canSend =
    !streaming &&
    !!currentSessionId &&
    ((!!text.trim() && (!file || uploadStatus === 'uploaded')) ||
      (!!file && uploadStatus === 'uploaded' && !!fileRef))

  return (
    <div className="border-line px-6 py-4">
      <div className="mx-auto max-w-3xl space-y-2">
        {file && (
          <div className="flex items-center gap-2 rounded-md border border-line px-3 py-2 text-body-sm">
            <Paperclip className="h-3.5 w-3.5 text-ink-tertiary shrink-0" />
            <span className="flex-1 truncate text-ink">{file.name}</span>
            <span className="text-label-sm text-ink-tertiary shrink-0">
              {(file.size / 1024).toFixed(1)} KB
            </span>

            {/* 上传状态指示 */}
            {uploadStatus === 'uploading' && (
              <span className="flex items-center gap-1 text-label-sm text-ink-tertiary shrink-0">
                <Loader2 className="h-3 w-3 animate-spin" />
                上传中
              </span>
            )}
            {uploadStatus === 'uploaded' && (
              <span
                className="flex items-center gap-1 text-label-sm text-success shrink-0"
                title={fileRef?.file_url}
              >
                <CheckCircle2 className="h-3 w-3" />
                已上传
              </span>
            )}
            {uploadStatus === 'error' && (
              <span
                className="flex items-center gap-1 text-label-sm text-danger shrink-0"
                title={uploadError ?? ''}
              >
                <AlertCircle className="h-3 w-3" />
                失败
              </span>
            )}

            <button
              type="button"
              onClick={handleRemoveFile}
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-ink-tertiary hover:bg-surface hover:text-ink"
              aria-label="移除附件"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}

        <div
          className={cn(
            'flex items-end gap-2 rounded-lg border border-line bg-surface px-3 py-2 transition-colors',
            'focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20',
          )}
        >
          <input
            ref={fileRefInput}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx"
            className="hidden"
            onChange={(e) => {
              const next = e.target.files?.[0]
              if (!next) return
              startUpload(next)
            }}
          />
          <button
            type="button"
            onClick={() => fileRefInput.current?.click()}
            disabled={streaming || !currentSessionId || (file != null && uploadStatus === 'uploading')}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-ink-tertiary hover:bg-surface-inset hover:text-ink disabled:opacity-40"
            aria-label="上传文件"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          <textarea
            ref={taRef}
            rows={1}
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              adjustHeight()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={
              currentSessionId
                ? '输入消息，Enter 发送，Shift+Enter 换行'
                : '请先选择或新建一个会话'
            }
            disabled={!currentSessionId || streaming}
            className="flex-1 resize-none bg-transparent text-body-md text-ink placeholder:text-ink-muted focus:outline-none disabled:opacity-40 max-h-[200px] leading-6 py-1.5"
          />

          <Button
            onClick={handleSend}
            disabled={!canSend}
            size="md"
            className="shrink-0"
            aria-label="发送"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>

        <p className="text-center text-label-sm text-ink-tertiary">
          AI 生成结果仅供参考，财务归档请以人工确认为准
        </p>
      </div>
    </div>
  )
}
