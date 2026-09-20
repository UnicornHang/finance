import { useEffect, useRef } from 'react'
import { Bot, Sparkles, Upload, FileText } from 'lucide-react'

import { useSessionStore, useCurrentMessages } from '@/stores/sessionStore'
import { sessionApi } from '@/api/chat'
import { MessageBubble } from './MessageBubble'

const QUICK_PROMPTS = [
  {
    icon: Upload,
    title: '上传发票归档',
    description: '拖拽发票图片或 PDF，AI 自动识别字段',
  },
  {
    icon: FileText,
    title: '审查合同',
    description: '上传合同 PDF，自动解析合规风险',
  },
  {
    icon: Sparkles,
    title: '差旅补贴标准',
    description: '询问出差去上海的住宿补贴',
  },
]

/**
 * Chat 主窗口
 * - 顶部轻量 context bar (会话名 / 思考状态)
 * - 消息流 (max-w-3xl 居中)
 * - 空状态：quick prompts 引导
 */
export function ChatWindow() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const messages = useCurrentMessages()
  const setMessages = useSessionStore((s) => s.setMessages)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (currentSessionId && messages.length === 0) {
      sessionApi.messages(currentSessionId).then((msgs) => setMessages(currentSessionId, msgs)).catch(() => {})
    }
  }, [currentSessionId, messages.length, setMessages])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  if (!currentSessionId) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="w-full max-w-2xl space-y-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary-tint text-primary">
            <Bot className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h2 className="text-headline-lg font-semibold text-ink">
              开始第一次对话
            </h2>
            <p className="text-body-md text-ink-tertiary">
              上传发票、查询制度、审查合同，AI 助手随时为你服务
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 text-left">
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q.title}
                className="group rounded-lg border border-line bg-surface p-4 text-left transition-colors hover:border-line-strong hover:bg-canvas"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded bg-canvas text-primary group-hover:bg-primary-tint">
                  <q.icon className="h-4 w-4" />
                </div>
                <p className="mt-3 text-title-lg font-semibold text-ink">
                  {q.title}
                </p>
                <p className="mt-1 text-body-sm text-ink-tertiary">
                  {q.description}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto"
    >
      <div className="mx-auto max-w-3xl px-6 py-8">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary-tint text-primary">
              <Sparkles className="h-6 w-6" />
            </div>
            <p className="mt-4 text-title-lg font-semibold text-ink">
              发送第一条消息开始对话
            </p>
            <p className="mt-1 text-body-sm text-ink-tertiary">
              支持文本、上传发票 PDF/图片、合同审查
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}