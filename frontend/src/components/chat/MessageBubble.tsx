import { Bot, CheckCheck, User } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { Message } from '@/types'

import { Markdown } from './Markdown'

interface Props {
  message: Message
}

/**
 * Chat 消息气泡
 * - User: 蓝色填充气泡，右对齐
 * - Assistant: 白底 hairline 边框气泡，左对齐 + 头像，渲染富文本（markdown 子集）
 * - 严格的 14px 字体，宽松行距
 */
export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  const isTool = message.role === 'tool'

  if (isTool) return null

  return (
    <div className={cn('flex items-end gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary-tint text-primary">
          <Bot className="h-4 w-4" />
        </div>
      )}

      <div className={cn('flex max-w-[80%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        <div
          data-slot="message-bubble"
          className={cn(
            'rounded-lg px-4 py-2.5 text-body-md',
            isUser
              ? 'bg-primary text-white'
              : 'bg-surface text-ink border border-line',
          )}
        >
          {!message.content ? (
            // 流式空状态：跳动小点
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
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          ) : (
            // Assistant：markdown 渲染（标题 / 列表 / 行内格式）
            <div className="break-words">
              <Markdown content={message.content} />
            </div>
          )}
        </div>

        {isUser && (
          <span className="flex items-center gap-1 text-label-sm text-ink-tertiary">
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
  )
}