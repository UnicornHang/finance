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

export const invoiceApi = {
  list: (params?: InvoiceListParams) =>
    apiClient
      .get<InvoiceListResponse>('/invoices/', { params })
      .then((r) => r.data),
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
