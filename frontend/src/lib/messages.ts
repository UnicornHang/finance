import type { Message, MessageAttachment, WebSource } from '@/types'

/** 助手消息是否为流式中断半截落库。 */
export function isInterruptedMessage(message: Message): boolean {
  return message.tool_calls?.interrupted === true
}

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

/** 校验单条 source 结构。 */
function isWebSource(s: unknown): s is WebSource {
  return (
    !!s &&
    typeof s === 'object' &&
    typeof (s as WebSource).index === 'number' &&
    typeof (s as WebSource).url === 'string'
  )
}

/** 从 assistant.tool_calls 取出制度 + 公开检索 sources（兼容嵌套）。 */
export function readSearchSources(message: Message): WebSource[] {
  const tc = message.tool_calls
  if (!tc || typeof tc !== 'object') return []

  const out: WebSource[] = []
  const seen = new Set<string>()

  const pushAll = (raw: unknown) => {
    if (!Array.isArray(raw)) return
    for (const s of raw) {
      if (!isWebSource(s)) continue
      const key = `${s.source_kind || ''}:${s.index}:${s.url}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push(s)
    }
  }

  // 制度：顶层 query_policy 或嵌套 policy
  if (tc.tool === 'query_policy') {
    pushAll(tc.sources)
  }
  const nestedPolicy = tc.policy
  if (nestedPolicy && typeof nestedPolicy === 'object') {
    pushAll((nestedPolicy as Record<string, unknown>).sources)
  }

  // 公开检索：顶层或嵌套 search
  const nestedSearch = tc.search
  if (nestedSearch && typeof nestedSearch === 'object') {
    pushAll((nestedSearch as Record<string, unknown>).sources)
  } else if (tc.tool === 'search_official_data') {
    pushAll(tc.sources)
  }

  return out
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
