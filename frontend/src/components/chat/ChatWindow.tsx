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

/** 三个快捷提示卡片 —— 「无会话」和「有会话但无消息」两种空状态共用 */
function QuickPrompts({ headline, subhead }: { headline: string; subhead: string }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-10">
      <div className="w-full max-w-2xl space-y-8 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary-tint text-primary">
          <Bot className="h-6 w-6" />
        </div>
        <div className="space-y-2">
          <h2 className="text-headline-lg font-semibold text-ink">{headline}</h2>
          <p className="text-body-md text-ink-tertiary">{subhead}</p>
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

/**
 * Chat 主窗口
 * - 空状态（无会话 / 有会话但无消息）：显示三个 quick prompts 引导
 * - 有消息：渲染消息流（max-w-3xl 居中）
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
      <QuickPrompts
        headline="开始第一次对话"
        subhead="上传发票、查询制度、审查合同，AI 助手随时为你服务"
      />
    )
  }

  if (messages.length === 0) {
    return (
      <QuickPrompts
        headline="开始你的第一次对话"
        subhead="上传发票、查询制度、审查合同，AI 助手随时为你服务"
      />
    )
  }

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="space-y-5">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
        </div>
      </div>
    </div>
  )
}