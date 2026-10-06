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

/**
 * 把档案入库状态映射成侧栏 archive_status。
 * 打开侧栏时会把 status 改成 ready，必须单独带归档态，否则已归档单据仍会显示「确定归档」。
 */
function archiveStatusFromDb(status: string | null | undefined): 'pending' | 'archived' | string | undefined {
  if (status === 'active') return 'archived'
  if (status === 'pending_review') return 'pending'
  return status ?? undefined
}

/**
 * 侧栏归档态：优先用接口查重后的 archive_status（档案已有相同代码+号码也算已归档）。
 */
export function resolveInvoiceArchiveStatus(invoice: {
  status?: string | null
  archive_status?: string | null
}): 'pending' | 'archived' | string | undefined {
  if (invoice.archive_status === 'archived' || invoice.status === 'active') {
    return 'archived'
  }
  if (invoice.archive_status === 'pending' || invoice.status === 'pending_review') {
    return 'pending'
  }
  return invoice.archive_status ?? archiveStatusFromDb(invoice.status)
}

/** 附件上的发票代码/号码（接口字段或识别落库的 extract_result）。 */
function invoiceCodeNumber(attachment: MessageAttachment): { code: string; number: string } | null {
  const code = (attachment.invoice_code || attachment.extract_result?.invoice_code || '').trim()
  const number = (attachment.invoice_number || attachment.extract_result?.invoice_number || '').trim()
  if (!code || !number) return null
  return { code, number }
}

/**
 * 同一张发票 / 同一份合同的稳定键。
 * 发票优先代码+号码（不同照片也算同一张），其次档案 id、文件哈希。
 */
export function documentIdentity(
  type: 'invoice' | 'contract',
  attachment: MessageAttachment,
): string {
  switch (type) {
    case 'invoice': {
      const pair = invoiceCodeNumber(attachment)
      if (pair) return `invoice:${pair.code}|${pair.number}`
      if (attachment.invoice_id) return `invoice-id:${attachment.invoice_id}`
      if (attachment.file_hash) return `invoice-hash:${attachment.file_hash}`
      return `invoice-att:${attachment.id ?? attachment.file_url}`
    }
    case 'contract': {
      if (attachment.contract_id) return `contract-id:${attachment.contract_id}`
      if (attachment.file_hash) return `contract-hash:${attachment.file_hash}`
      return `contract-att:${attachment.id ?? attachment.file_url}`
    }
    default: {
      const unreachable: never = type
      return unreachable
    }
  }
}

/** 当前侧栏正在看的单据，用来高亮下拉项。 */
export function panelDocumentIdentity(
  type: 'invoice' | 'contract' | null,
  data: unknown,
): string | null {
  if (type !== 'invoice' && type !== 'contract') return null
  if (!data || typeof data !== 'object') return null
  const rec = data as Record<string, unknown>
  const attachment: MessageAttachment = {
    file_url: typeof rec.file_url === 'string' ? rec.file_url : '',
    file_hash: typeof rec.file_hash === 'string' ? rec.file_hash : '',
    invoice_id: typeof rec.invoice_id === 'string' ? rec.invoice_id : null,
    invoice_code: typeof rec.invoice_code === 'string' ? rec.invoice_code : null,
    invoice_number: typeof rec.invoice_number === 'string' ? rec.invoice_number : null,
    contract_id: typeof rec.contract_id === 'string' ? rec.contract_id : null,
  }
  return documentIdentity(type, attachment)
}

/**
 * 列出本会话可查看的发票/合同（时间正序）。
 * 同一张发票或同一份合同只保留最近一次识别，避免审查结果下拉里重复出现。
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
  const unique = new Map<string, HistoryDocumentTurn>()
  for (const turn of turns) {
    unique.set(documentIdentity(turn.type, turn.attachment), turn)
  }
  return [...unique.values()]
}

/**
 * 看最后一条带发票/合同附件的用户消息。
 * 用户后来又发了普通文字，则仍返回最近一份单据（便于重开会话）。
 */
export function latestHistorySidePanel(messages: Message[]): HistoryDocumentTurn | null {
  const turns = listHistoryDocumentTurns(messages)
  return turns.length ? turns[turns.length - 1] : null
}

/** 按某个附件找回对应轮次（含紧随其后的助手审查摘要）。同一张发票点任一次上传都打开那条结果。 */
export function findDocumentTurnForAttachment(
  messages: Message[],
  attachment: MessageAttachment,
): HistoryDocumentTurn | null {
  const type = documentKind(attachment)
  if (type !== 'invoice' && type !== 'contract') return null
  const key = documentIdentity(type, attachment)
  return (
    listHistoryDocumentTurns(messages).find(
      (turn) => documentIdentity(turn.type, turn.attachment) === key,
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
      openSidePanel('invoice', {
        ...invoice,
        status: 'ready',
        invoice_id: invoice.id,
        archive_status: resolveInvoiceArchiveStatus(invoice),
      })
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
        archive_status: resolveInvoiceArchiveStatus(preview.invoice),
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
        contract.archive_status === 'archived' || contract.status === 'active'
          ? 'archived'
          : contract.archive_status === 'pending' || contract.status === 'pending_review'
            ? 'pending'
            : contract.status
      // 档案摘要若被确认接口脏写覆盖，优先用当轮助手回复展示
      const storedSummary = contract.review_result?.summary?.trim() || ''
      const replySummary = reply?.trim() || ''
      const useReplySummary =
        !!replySummary &&
        (storedSummary.length < 40 ||
          (replySummary.length > storedSummary.length + 80 &&
            !storedSummary.includes(replySummary.slice(0, Math.min(40, replySummary.length)))))
      openSidePanel('contract', {
        ...contract,
        status: 'ready',
        contract_id: contract.id,
        archive_status: archiveStatus,
        chat_file_id: attachment.id ?? null,
        review_result: useReplySummary
          ? {
              ...(contract.review_result || {}),
              summary: replySummary,
              violations: contract.review_result?.violations || [],
            }
          : contract.review_result,
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
