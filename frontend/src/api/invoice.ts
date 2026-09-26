import { apiClient } from './client'
import type { Invoice, InvoiceFileResponse, InvoicePreviewResponse } from '@/types'

export interface InvoiceListParams {
  page?: number
  page_size?: number
  invoice_type?: string
  search?: string
  start_date?: string
  end_date?: string
  status_filter?: string
}

export interface InvoiceListResponse {
  items: Invoice[]
  total: number
  page: number
  page_size: number
}

const LIST_PAGE_CAP = 100
const EVERY_STATUS = ['pending_review', 'active', 'deleted'] as const

function listInvoices(params?: InvoiceListParams) {
  return apiClient
    .get<InvoiceListResponse>('/invoices/', { params })
    .then((r) => r.data)
}

/** 按一个真实状态把分页结果取完。接口单页最多 100 条。 */
async function listStatusPages(status: string, invoiceType?: string): Promise<Invoice[]> {
  const collected: Invoice[] = []
  let page = 1
  let total = 0
  do {
    const res = await listInvoices({
      page,
      page_size: LIST_PAGE_CAP,
      status_filter: status,
      invoice_type: invoiceType,
    })
    total = res.total
    collected.push(...res.items)
    page += 1
  } while (collected.length < total && page <= 20)
  return collected
}

/**
 * 全部状态：分别查待确认、已归档、已删除再合并。
 * 不能传 status_filter=all，服务端会当成等值条件，库里没有这个状态，列表就是空的。
 */
async function listAllStatuses(params: {
  page?: number
  page_size?: number
  invoice_type?: string
}): Promise<InvoiceListResponse> {
  const page = params.page ?? 1
  const pageSize = params.page_size ?? 20
  const groups = await Promise.all(
    EVERY_STATUS.map((status) => listStatusPages(status, params.invoice_type)),
  )
  const merged = groups
    .flat()
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
  const start = (page - 1) * pageSize
  return {
    items: merged.slice(start, start + pageSize),
    total: merged.length,
    page,
    page_size: pageSize,
  }
}

export const invoiceApi = {
  list: listInvoices,
  listAllStatuses,
  get: (id: string) => apiClient.get<Invoice>(`/invoices/${id}`).then((r) => r.data),
  archive: (data: Partial<Invoice> & { file_url: string; file_hash: string }) =>
    apiClient.post<Invoice>('/invoices/archive', data).then((r) => r.data),
  update: (id: string, data: Partial<Invoice>) =>
    apiClient.patch<Invoice>(`/invoices/${id}`, data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/invoices/${id}`).then((r) => r.data),

  // Phase A
  /** pending_review → active；最后一次编辑机会 */
  confirm: (id: string, data: Partial<Invoice> = {}) =>
    apiClient
      .post<Invoice>(`/invoices/${id}/confirm`, data)
      .then((r) => r.data),

  /** 前端轮询查 OCR 结果 */
  previewByHash: (fileHash: string) =>
    apiClient
      .get<InvoicePreviewResponse>(`/invoices/preview/by-hash/${fileHash}`)
      .then((r) => r.data),

  /** 获取 MinIO 预签名下载 URL */
  downloadUrl: (id: string, expires = 3600) =>
    apiClient
      .get<InvoiceFileResponse>(`/invoices/${id}/file`, {
        params: { expires },
      })
      .then((r) => r.data),
}
