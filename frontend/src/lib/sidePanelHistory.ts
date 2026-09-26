import { contractApi } from '@/api/contract'
import { invoiceApi } from '@/api/invoice'
import { readAttachments } from '@/lib/messages'
import { useUIStore } from '@/stores/uiStore'
import type { Message, MessageAttachment } from '@/types'

/** 当前会话最后一轮若是发票或合同，切回来时要重开的侧栏。 */
export type HistoryDocumentTurn =
  | { type: 'invoice'; attachment: MessageAttachment; reply: string | null }
  | { type: 'contract'; attachment: MessageAttachment; reply: string | null }

/**
 * 附件属于发票还是合同。
 * 已有分类结果时以 intent 为准；只有历史数据没写 intent 时，才按文件名兜底。
 */
function documentKind(attachment: MessageAttachment): 'invoice' | 'contract' | null {
  if (attachment.intent === 'invoice' || attachment.intent === 'contract') {
    return attachment.intent
  }
  if (attachment.intent === 'chat') return null
  const name = attachment.original_filename ?? ''
  if (/发票/.test(name) || /invoice/i.test(name)) return 'invoice'
  if (/合同|协议/.test(name) || /contract/i.test(name)) return 'contract'
  return null
}

/** 识别还在跑，侧栏应停在处理中，而不是去拉一份还不存在的单据。 */
function isInFlight(status: string | null | undefined): boolean {
  return status === 'pending' || status === 'running'
}

/**
 * 看最后一条用户消息，而不是最后一条助手回复。
 * 助手回复只是这一轮的说明；发票/合同附件挂在用户消息上。
 * 用户后来又发了普通文字，则最后一轮不再是单据，返回 null。
 */
export function latestHistorySidePanel(messages: Message[]): HistoryDocumentTurn | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role !== 'user') continue

    const attachment = readAttachments(message).find((item) => documentKind(item) !== null)
    if (!attachment || attachment.recognize_status === 'failed') return null

    const type = documentKind(attachment)
    if (type !== 'invoice' && type !== 'contract') return null

    const reply =
      messages.slice(index + 1).find((item) => item.role === 'assistant')?.content ?? null
    return { type, attachment, reply }
  }
  return null
}

/** 按历史消息恢复右侧栏；会话已经切走时 isCancelled 为 true，不再写入。 */
export async function restoreSidePanelFromHistory(
  messages: Message[],
  isCancelled: () => boolean,
): Promise<void> {
  const target = latestHistorySidePanel(messages)
  if (isCancelled()) return
  if (!target) {
    useUIStore.getState().closeSidePanel()
    return
  }

  switch (target.type) {
    case 'invoice':
      await restoreInvoice(target.attachment, isCancelled)
      return
    case 'contract':
      await restoreContract(target.attachment, target.reply, isCancelled)
      return
    default: {
      const unreachable: never = target
      return unreachable
    }
  }
}

/** 用发票 id 或文件哈希把识别结果填回侧栏。 */
async function restoreInvoice(
  attachment: MessageAttachment,
  isCancelled: () => boolean,
): Promise<void> {
  const { openSidePanel, closeSidePanel } = useUIStore.getState()
  const fileHash = attachment.file_hash
  const processing = {
    status: 'processing' as const,
    file_url: attachment.file_url,
    file_hash: fileHash,
  }

  if (isInFlight(attachment.recognize_status)) {
    if (!fileHash) {
      closeSidePanel()
      return
    }
    openSidePanel('invoice', processing)
    return
  }

  try {
    if (attachment.invoice_id) {
      const invoice = await invoiceApi.get(attachment.invoice_id)
      if (isCancelled()) return
      openSidePanel('invoice', { ...invoice, status: 'ready', invoice_id: invoice.id })
      return
    }
    if (!fileHash) {
      closeSidePanel()
      return
    }
    const preview = await invoiceApi.previewByHash(fileHash)
    if (isCancelled()) return
    if (preview.status === 'ready' && preview.invoice) {
      openSidePanel('invoice', {
        ...preview.invoice,
        status: 'ready',
        invoice_id: preview.invoice.id,
      })
      return
    }
    if (preview.status === 'processing') {
      openSidePanel('invoice', processing)
      return
    }
    closeSidePanel()
  } catch {
    if (!isCancelled()) closeSidePanel()
  }
}

/** 有合同档案就打开档案；否则用这一轮的助手回复作为审查摘要。 */
async function restoreContract(
  attachment: MessageAttachment,
  reply: string | null,
  isCancelled: () => boolean,
): Promise<void> {
  const { openSidePanel, closeSidePanel } = useUIStore.getState()
  if (isInFlight(attachment.recognize_status)) {
    openSidePanel('contract', {
      status: 'processing',
      contract_name: attachment.original_filename,
      file_url: attachment.file_url,
      file_hash: attachment.file_hash,
    })
    return
  }

  if (attachment.contract_id) {
    try {
      const contract = await contractApi.get(attachment.contract_id)
      if (isCancelled()) return
      openSidePanel('contract', { ...contract, status: 'ready' })
      return
    } catch {
      // 档案已删时仍展示当轮审查文字
    }
  }

  if (isCancelled()) return
  if (!reply && !attachment.original_filename) {
    closeSidePanel()
    return
  }
  openSidePanel('contract', {
    status: 'ready',
    contract_name: attachment.original_filename ?? '',
    file_url: attachment.file_url,
    file_hash: attachment.file_hash,
    review_result: reply ? { summary: reply, violations: [] } : undefined,
  })
}
