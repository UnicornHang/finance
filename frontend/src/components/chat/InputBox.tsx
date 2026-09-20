import { useRef, useState } from 'react'
import { Paperclip, Send, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useSessionStore } from '@/stores/sessionStore'
import { useUIStore } from '@/stores/uiStore'
import { useChat } from '@/hooks/useSSE'
import { cn } from '@/lib/utils'

/**
 * 输入框
 * - 多行自适应
 * - 文件 chip 在选择后浮于上方
 * - 左侧附件 + 右侧发送按钮 (实色)
 */
export function InputBox() {
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const streaming = useUIStore((s) => s.streaming)
  const { send } = useChat()

  const adjustHeight = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }

  const handleSend = async () => {
    if (!text.trim() || !currentSessionId || streaming) return
    const msg = text
    const f = file
    setText('')
    setFile(null)
    if (taRef.current) taRef.current.style.height = 'auto'
    await send(msg, f || undefined)
  }

  return (
    <div className="border-t border-line bg-surface px-6 py-4">
      <div className="mx-auto max-w-3xl space-y-2">
        {file && (
          <div className="flex items-center gap-2 rounded-md border border-line bg-surface-inset px-3 py-2 text-body-sm">
            <Paperclip className="h-3.5 w-3.5 text-ink-tertiary shrink-0" />
            <span className="flex-1 truncate text-ink">{file.name}</span>
            <span className="text-label-sm text-ink-tertiary shrink-0">
              {(file.size / 1024).toFixed(1)} KB
            </span>
            <button
              onClick={() => setFile(null)}
              className="flex h-5 w-5 items-center justify-center rounded text-ink-tertiary hover:bg-surface hover:text-ink"
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
            ref={fileRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={streaming || !currentSessionId}
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
            disabled={!text.trim() || streaming || !currentSessionId}
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