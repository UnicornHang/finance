import type { Message, MessageAttachment } from '@/types'

/** 从消息上取出附件：优先用 attachments，否则读 tool_calls.attachments。 */
export function readAttachments(message: Message): MessageAttachment[] {
  if (message.attachments?.length) {
    return message.attachments.filter(Boolean)
  }
  const nested = message.tool_calls?.attachments
  if (!Array.isArray(nested)) return []
  return nested.filter(
    (item): item is MessageAttachment =>
      !!item &&
      typeof item === 'object' &&
      'file_url' in item &&
      typeof item.file_url === 'string',
  )
}

/** 把附件字段补齐，历史接口和乐观消息用同一结构。 */
export function withAttachments(messages: Message[]): Message[] {
  return messages.map((message) => {
    const attachments = readAttachments(message)
    if (!attachments.length) return message
    return { ...message, attachments }
  })
}

/**
 * 流式气泡前面会拼进度句（「正在判断这份文件…」），落库正文是其后的模型回复。
 * 两者算同一轮，不能再把临时气泡接到历史后面。
 */
function isSameTurn(saved: Message, localMsg: Message): boolean {
  if (saved.role !== localMsg.role) return false
  const savedText = (saved.content || '').trim()
  const localText = (localMsg.content || '').trim()
  if (savedText === localText) return true
  if (!savedText || !localText) return false
  return localText.endsWith(savedText) && savedText.length >= 8
}

/**
 * 用服务端消息替换已落库的临时消息，并保留还没出现在服务端的本地附件消息。
 * 避免「拉历史」把刚发出的图片/文件盖掉，也不要把同一段回复再渲染一遍。
 */
export function mergeMessages(server: Message[], local: Message[]): Message[] {
  const normalized = withAttachments(server)
  const consumed = new Set<string>()
  const extras: Message[] = []

  for (const localMsg of local) {
    const localAttachments = readAttachments(localMsg)
    const localHash = localAttachments[0]?.file_hash
    // 服务端还没有这份文件时，保留本地气泡，避免旧的历史响应把附件清掉
    if (localHash) {
      const onServer = normalized.some(
        (saved) =>
          saved.role === localMsg.role &&
          readAttachments(saved).some((att) => att.file_hash === localHash),
      )
      if (!onServer) {
        extras.push({ ...localMsg, attachments: localAttachments })
      }
      continue
    }
    if (!localMsg.id.startsWith('tmp-')) continue
    const match = normalized.find((saved) => {
      if (consumed.has(saved.id)) return false
      return isSameTurn(saved, localMsg)
    })
    if (match) {
      consumed.add(match.id)
      continue
    }
    extras.push(localMsg)
  }

  return [...normalized, ...extras]
}
