import { apiClient } from './client'
import type { Contract } from '@/types'

export interface ContractListParams {
  page?: number
  page_size?: number
  search?: string
  risk_level?: string
}

export interface ContractListResponse {
  items: Contract[]
  total: number
  page: number
  page_size: number
  /** 全部已归档合同的风险分布（不受 search/risk 筛选影响） */
  risk_counts: {
    high: number
    medium: number
    low: number
  }
}

export const contractApi = {
  list: (params?: ContractListParams) =>
    apiClient.get<ContractListResponse>('/contracts/', { params }).then((r) => r.data),
  get: (id: string) => apiClient.get<Contract>(`/contracts/${id}`).then((r) => r.data),
  /** 兼容旧入口：仅写入 pending_review，不直接归档 */
  archive: (
    data: Partial<Contract> & {
      file_url: string
      file_hash: string
      chat_file_id?: string
      review_result?: { violations?: unknown[]; summary?: string; risk_level?: string } | null
    },
  ) => apiClient.post<Contract>('/contracts/archive', data).then((r) => r.data),
  /** pending_review → active；最后一次编辑机会 */
  confirm: (id: string, data: Partial<Contract> = {}) =>
    apiClient.post<Contract>(`/contracts/${id}/confirm`, data).then((r) => r.data),
  /** 按原件重新审查，覆盖摘要与概览字段 */
  reReview: (id: string) =>
    apiClient.post<Contract>(`/contracts/${id}/review`).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/contracts/${id}`),
}
