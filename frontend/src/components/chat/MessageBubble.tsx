import { useEffect, useState } from 'react'
import {
  Bot,
  CheckCheck,
  FileText,
  ImageIcon,
  Loader2,
  User,
} from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { fileApi } from '@/api/file'
import { cn } from '@/lib/utils'
import type { Message, MessageAttachment } from '@/types'

import { Markdown } from './Markdown'

interface Props {
  message: Message
}

const IMAGE_EXT_RE = /\.(jpe?g|png|webp|gif|bmp|heic|heif|jfif)$/i

/** 判断是否为图片类型附件（走图片预览，不走文件卡） */
function isImageAttachment(att: MessageAttachment): boolean {
  const ct = (att.content_type || '').toLowerCase()
  if (ct.startsWith('image/')) return true
  return IMAGE_EXT_RE.test(att.original_filename || '')
}

/** 判断是否为 PDF（预览弹窗用） */
function isPdfAttachment(att: MessageAttachment): boolean {
  const ct = (att.content_type || '').toLowerCase()
  if (ct === 'application/pdf' || ct.includes('pdf')) return true
  return (att.original_filename || '').toLowerCase().endsWith('.pdf')
}

/** 展示用文件大小，如 13.3KB */
function formatSize(size?: number | null): string {
  if (size == null || Number.isNaN(size)) return ''
  if (size < 1024) return `${size}B`
  if (size < 1024 * 1024) {
    const kb = size / 1024
    return `${kb >= 10 ? kb.toFixed(0) : kb.toFixed(1)}KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)}MB`
}

/** 从文件名或 MIME 推断扩展名展示，如 DOCX / PDF */
function fileExtLabel(att: MessageAttachment): string {
  const name = att.original_filename || ''
  const dot = name.lastIndexOf('.')
  if (dot >= 0 && dot < name.length - 1) {
    return name.slice(dot + 1).toUpperCase()
  }
  const ct = (att.content_type || '').toLowerCase()
  if (ct.includes('pdf')) return 'PDF'
  if (ct.includes('word') || ct.includes('document')) return 'DOCX'
  return 'FILE'
}

/**
 * 图片附件：按图片格式展示（圆角大图，可点击预览）
 * 与文件卡完全不同的视觉形态
 */
function ImageAttachment({
  attachment,
  onPreview,
}: {
  attachment: MessageAttachment
  onPreview: (att: MessageAttachment) => void
}) {
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)
  const [thumbLoading, setThumbLoading] = useState(true)
  const name = attachment.original_filename || '图片'

  useEffect(() => {
    let cancelled = false
    setThumbLoading(true)
    setThumbUrl(null)
    fileApi
      .presign(attachment.file_url)
      .then((r) => {
        if (!cancelled) setThumbUrl(r.url)
      })
      .catch(() => {
        if (!cancelled) setThumbUrl(null)
      })
      .finally(() => {
        if (!cancelled) setThumbLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [attachment.file_url])

  return (
    <button
      type="button"
      onClick={() => onPreview(attachment)}
      className="group block max-w-[280px] overflow-hidden rounded-2xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      aria-label={`预览图片 ${name}`}
    >
      {thumbLoading && (
        <div className="flex h-40 w-[220px] items-center justify-center rounded-2xl bg-canvas">
          <Loader2 className="h-6 w-6 animate-spin text-ink-tertiary" />
        </div>
      )}
      {!thumbLoading && thumbUrl && (
        <img
          src={thumbUrl}
          alt={name}
          className="block max-h-[360px] w-auto max-w-full rounded-2xl object-contain transition-opacity group-hover:opacity-95"
        />
      )}
      {!thumbLoading && !thumbUrl && (
        <div className="flex h-40 w-[220px] flex-col items-center justify-center gap-2 rounded-2xl bg-canvas text-body-sm text-ink-secondary">
          <ImageIcon className="h-8 w-8 text-ink-tertiary" />
          <span>图片加载失败</span>
        </div>
      )}
    </button>
  )
}

/**
 * 文件附件：文件信息卡（图标 + 文件名 + 类型/大小）
 * 仅用于非图片（PDF / Word 等），不用于图片
 */
function FileAttachment({
  attachment,
  onPreview,
}: {
  attachment: MessageAttachment
  onPreview: (att: MessageAttachment) => void
}) {
  const name = attachment.original_filename || '附件'
  const metaLine = [fileExtLabel(attachment), formatSize(attachment.size)]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type="button"
      onClick={() => onPreview(attachment)}
      className="flex w-[min(100%,280px)] items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3 text-left shadow-sm transition-colors hover:bg-canvas"
      aria-label={`预览文件 ${name}`}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-tint">
        <FileText className="h-5 w-5 text-primary" strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-body-md font-medium text-ink">{name}</p>
        {metaLine && (
          <p className="mt-0.5 truncate text-label-sm text-ink-tertiary">
            {metaLine}
          </p>
        )}
      </div>
    </button>
  )
}

/** 按类型分流：图片 → ImageAttachment；文件 → FileAttachment */
function AttachmentCard({
  attachment,
  onPreview,
}: {
  attachment: MessageAttachment
  onPreview: (att: MessageAttachment) => void
}) {
  if (isImageAttachment(attachment)) {
    return <ImageAttachment attachment={attachment} onPreview={onPreview} />
  }
  return <FileAttachment attachment={attachment} onPreview={onPreview} />
}

/**
 * 附件预览弹窗：图片全图 / PDF iframe / 其他类型提供新窗口打开
 */
function AttachmentPreviewDialog({
  attachment,
  open,
  onOpenChange,
}: {
  attachment: MessageAttachment | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !attachment) {
      setUrl(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    setUrl(null)
    fileApi
      .presign(attachment.file_url)
      .then((r) => {
        if (!cancelled) setUrl(r.url)
      })
      .catch(() => {
        if (!cancelled) setError('无法加载预览')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, attachment])

  const name = attachment?.original_filename || '文件预览'
  const isImage = attachment ? isImageAttachment(attachment) : false
  const isPdf = attachment ? isPdfAttachment(attachment) : false

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-hidden">
        <DialogHeader>
          <DialogTitle className="truncate pr-8">{name}</DialogTitle>
        </DialogHeader>
        <div className="mt-2 flex min-h-[240px] items-center justify-center">
          {loading && (
            <Loader2 className="h-8 w-8 animate-spin text-ink-tertiary" />
          )}
          {!loading && error && (
            <p className="text-body-md text-danger">{error}</p>
          )}
          {!loading && !error && url && isImage && (
            <img
              src={url}
              alt={name}
              className="max-h-[75vh] max-w-full object-contain"
            />
          )}
          {!loading && !error && url && isPdf && (
            <iframe
              src={url}
              title={name}
              className="h-[75vh] w-full rounded-md border border-line"
            />
          )}
          {!loading && !error && url && !isImage && !isPdf && (
            <div className="space-y-3 text-center">
              <FileText className="mx-auto h-10 w-10 text-ink-tertiary" />
              <p className="text-body-md text-ink-secondary">
                该文件类型暂不支持内嵌预览
              </p>
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex text-body-md text-primary underline"
              >
                在新窗口打开 / 下载
              </a>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Chat 消息气泡
 * - 用户：图片按大图预览、文件按信息卡，二者形态不同；文字独立气泡（原有主色白字）
 * - 助手：白底边框气泡 + 头像，markdown 渲染
 */
export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  const isTool = message.role === 'tool'
  const attachments = message.attachments?.filter(Boolean) ?? []
  const hasAttachments = attachments.length > 0
  const placeholderContents = new Set(['（上传了发票文件）', '（上传了文件）'])
  const showText =
    !!message.content &&
    !(hasAttachments && placeholderContents.has(message.content.trim()))
  const showStreamingDots = !message.content && !hasAttachments

  const [previewAtt, setPreviewAtt] = useState<MessageAttachment | null>(null)

  if (isTool) return null

  return (
    <>
      <div
        className={cn(
          'flex items-end gap-3',
          isUser ? 'justify-end' : 'justify-start',
        )}
      >
        {!isUser && (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary-tint text-primary">
            <Bot className="h-4 w-4" />
          </div>
        )}

        <div
          className={cn(
            'flex w-full max-w-[80%] flex-col gap-2',
            isUser ? 'items-end' : 'items-start',
          )}
        >
          {hasAttachments && (
            <div
              data-slot="message-attachments"
              className={cn(
                'flex flex-col gap-2',
                isUser ? 'items-end' : 'items-start',
              )}
            >
              {attachments.map((att) => (
                <AttachmentCard
                  key={`${att.file_hash}-${att.file_url}`}
                  attachment={att}
                  onPreview={setPreviewAtt}
                />
              ))}
            </div>
          )}

          {(showText || showStreamingDots) && (
            <div
              data-slot="message-bubble"
              className={cn(
                'max-w-full rounded-2xl px-4 py-2.5 text-body-md',
                isUser
                  ? 'self-end bg-primary text-white'
                  : 'bg-surface text-ink border border-line',
              )}
            >
              {showStreamingDots ? (
                <span className="inline-flex gap-1 text-ink-tertiary">
                  <span className="h-1.5 w-1.5 animate-stream-blink rounded-full bg-ink-tertiary" />
                  <span
                    className="h-1.5 w-1.5 animate-stream-blink rounded-full bg-ink-tertiary"
                    style={{ animationDelay: '0.15s' }}
                  />
                  <span
                    className="h-1.5 w-1.5 animate-stream-blink rounded-full bg-ink-tertiary"
                    style={{ animationDelay: '0.3s' }}
                  />
                </span>
              ) : isUser ? (
                <div className="whitespace-pre-wrap break-words">
                  {message.content}
                </div>
              ) : (
                <div className="break-words">
                  <Markdown content={message.content!} />
                </div>
              )}
            </div>
          )}

          {isUser && (
            <span className="flex items-center gap-1 self-end text-label-sm text-ink-tertiary">
              <CheckCheck className="h-3 w-3" />
              已发送
            </span>
          )}
        </div>

        {isUser && (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-inset text-ink-secondary">
            <User className="h-4 w-4" />
          </div>
        )}
      </div>

      <AttachmentPreviewDialog
        attachment={previewAtt}
        open={!!previewAtt}
        onOpenChange={(open) => {
          if (!open) setPreviewAtt(null)
        }}
      />
    </>
  )
}
