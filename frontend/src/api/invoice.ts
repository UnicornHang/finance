import { apiClient } from './client'
import type { Invoice } from '@/types'

export const invoiceApi = {
  list: (params?: Record<string, unknown>) =>
    apiClient.get<Invoice[]>('/invoices/', { params }).then((r) => r.data),
  get: (id: string) => apiClient.get<Invoice>(`/invoices/${id}`).then((r) => r.data),
  archive: (data: Partial<Invoice> & { file_url: string; file_hash: string }) =>
    apiClient.post<Invoice>('/invoices/archive', data).then((r) => r.data),
  update: (id: string, data: Partial<Invoice>) =>
    apiClient.patch<Invoice>(`/invoices/${id}`, data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/invoices/${id}`),
}