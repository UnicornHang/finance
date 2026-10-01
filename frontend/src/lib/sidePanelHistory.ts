import { contractApi } from '@/api/contract'
import { fileApi } from '@/api/file'
import { invoiceApi } from '@/api/invoice'
import { readAttachments } from '@/lib/messages'
import { useUIStore } from '@/stores/uiStore'
import type { Message, MessageAttachment } from '@/types'

/** 当前会话里某一轮发票或合同，可点开右侧栏查看。 */
export type HistoryDocumentTurn =
  | { type: 'invoice'; attachment: MessageAttachment; reply: string | null }
  | { type: 'contract'; attachment: MessageAttachment; reply: string | null }

/**
 * 附件属于发票还是合同。
 * 已有分类结果时以 intent 为准；只有历史数据没写 intent 时，才按文件名兜底。
 */
export function documentKind(attachment: MessageAttachment): 'invoice' | 'contract' | null {
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

/** 同一附件：优先 id，其次 file_hash。 */
function sameAttachment(a: MessageAttachment, b: MessageAttachment): boolean {
  if (a.id && b.id) return a.id === b.id
  return Boolean(a.file_hash && a.file_hash === b.file_hash)
}

/**
 * 列出本会话全部可查看的发票/合同轮次（时间正序）。
 * 多份合同时右侧栏默认只开最新一份，其余靠点击附件切换。
 */
export function listHistoryDocumentTurns(messages: Message[]): HistoryDocumentTurn[] {
  const turns: HistoryDocumentTurn[] = []
  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index]
    if (message.role !== 'user') continue

    for (const attachment of readAttachments(message)) {
      if (attachment.recognize_status === 'failed') continue
      const type = documentKind(attachment)
      if (type !== 'invoice' && type !== 'contract') continue
      const reply =
        messages.slice(index + 1).find((item) => item.role === 'assistant')?.content ?? null
      turns.push({ type, attachment, reply })
    }
  }
  return turns
}

/**
 * 看最后一条带发票/合同附件的用户消息。
 * 用户后来又发了普通文字，则仍返回最近一份单据（便于重开会话）。
 */
export function latestHistorySidePanel(messages: Message[]): HistoryDocumentTurn | null {
  const turns = listHistoryDocumentTurns(messages)
  return turns.length ? turns[turns.length - 1] : null
}

/** 按某个附件找回对应轮次（含紧随其后的助手审查摘要）。 */
export function findDocumentTurnForAttachment(
  messages: Message[],
  attachment: MessageAttachment,
): HistoryDocumentTurn | null {
  return (
    listHistoryDocumentTurns(messages).find((turn) =>
      sameAttachment(turn.attachment, attachment),
    ) ?? null
  )
}

/** 打开某一轮发票/合同的右侧栏。 */
export async function openHistoryDocument(
  turn: HistoryDocumentTurn,
  isCancelled: () => boolean = () => false,
): Promise<void> {
  switch (turn.type) {
    case 'invoice':
      await restoreInvoice(turn.attachment, isCancelled)
      return
    case 'contract':
      await restoreContract(turn.attachment, turn.reply, isCancelled)
      return
    default: {
      const unreachable: never = turn
      return unreachable
    }
  }
}

/** 按历史消息恢复右侧栏；会话已经切走时 isCancelled 为 true，不再写入。 */
export async function restoreSidePanelFromHistory(
  messages: Message[],
  isCancelled: () => boolean,
): Promise<void> {
  const target = latestHistorySidePanel(messages)
  if (isCancelled()) return
  if (!target) {
    useUIStore.getState().clearSidePanel()
    return
  }
  await openHistoryDocument(target, isCancelled)
}

/** 用发票 id 或文件哈希把识别结果填回侧栏。 */
async function restoreInvoice(
  attachment: MessageAttachment,
  isCancelled: () => boolean,
): Promise<void> {
  const { openSidePanel, clearSidePanel } = useUIStore.getState()
  const fileHash = attachment.file_hash
  const processing = {
    status: 'processing' as const,
    file_url: attachment.file_url,
    file_hash: fileHash,
  }

  if (isInFlight(attachment.recognize_status)) {
    if (!fileHash) {
      clearSidePanel()
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
      clearSidePanel()
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
    clearSidePanel()
  } catch {
    if (!isCancelled()) clearSidePanel()
  }
}

/** 有合同档案就打开档案；否则用附件上的抽取字段 + 助手回复恢复侧栏。 */
async function restoreContract(
  attachment: MessageAttachment,
  reply: string | null,
  isCancelled: () => boolean,
): Promise<void> {
  const { openSidePanel, clearSidePanel } = useUIStore.getState()
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
      const archiveStatus =
        contract.status === 'active'
          ? 'archived'
          : contract.status === 'pending_review'
            ? 'pending'
            : contract.status
      openSidePanel('contract', {
        ...contract,
        status: 'ready',
        contract_id: contract.id,
        archive_status: archiveStatus,
        chat_file_id: attachment.id ?? null,
      })
      return
    } catch {
      // 档案已删时仍展示当轮审查文字
    }
  }

  if (isCancelled()) return
  if (!reply && !attachment.original_filename) {
    clearSidePanel()
    return
  }

  // 优先用审查时落库的字段；老消息没有则按文件再抽一次
  let extract = attachment.extract_result ?? null
  const missingFields =
    !extract?.party_a && !extract?.party_b && extract?.amount == null && !extract?.sign_date
  if (missingFields && attachment.id) {
    try {
      extract = await fileApi.contractExtract(attachment.id)
    } catch {
      // 补抽失败仍展示摘要，字段留空
    }
  }
  if (isCancelled()) return

  openSidePanel('contract', {
    status: 'ready',
    contract_name: extract?.contract_name || attachment.original_filename || '',
    party_a: extract?.party_a ?? null,
    party_b: extract?.party_b ?? null,
    sign_date: extract?.sign_date ?? null,
    amount: extract?.amount ?? null,
    file_url: attachment.file_url,
    file_hash: attachment.file_hash,
    chat_file_id: attachment.id ?? null,
    contract_id: attachment.contract_id ?? null,
    review_result: reply ? { summary: reply, violations: [] } : undefined,
  })
}
