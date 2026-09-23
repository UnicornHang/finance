import { apiClient } from './client'
import type { Contract } from '@/types'

export const contractApi = {
  list: (params?: Record<string, unknown>) =>
    apiClient.get<Contract[]>('/contracts/', { params }).then((r) => r.data),
  get: (id: string) => apiClient.get<Contract>(`/contracts/${id}`).then((r) => r.data),
  archive: (data: Partial<Contract> & { file_url: string; file_hash: string }) =>
    apiClient.post<Contract>('/contracts/archive', data).then((r) => r.data),
  reReview: (id: string) =>
    apiClient.post<Contract>(`/contracts/${id}/review`).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/contracts/${id}`),
}
