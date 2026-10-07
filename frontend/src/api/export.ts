import { apiClient } from './client'
import type {
  ExportDownloadResponse,
  ExportJob,
  ExportJobListResponse,
  ExportResourceType,
} from '@/types'

/** 创建导出任务请求体 */
export interface ExportCreateParams {
  resource_type: ExportResourceType
  filters?: Record<string, unknown>
}

/** 导出任务列表查询参数 */
export interface ExportListParams {
  resource_type?: ExportResourceType
  page?: number
  page_size?: number
}

/** 异步导出中心 API（/exports） */
export const exportApi = {
  /** 创建导出任务；进行中同 fingerprint 幂等返回 */
  create: (data: ExportCreateParams) =>
    apiClient
      .post<ExportJob>('/exports/', {
        resource_type: data.resource_type,
        filters: data.filters ?? {},
      })
      .then((r) => r.data),

  /** 分页列出当前用户的导出任务 */
  list: (params?: ExportListParams) =>
    apiClient
      .get<ExportJobListResponse>('/exports/', { params })
      .then((r) => r.data),

  /** 导出任务详情 */
  get: (id: string) =>
    apiClient.get<ExportJob>(`/exports/${id}`).then((r) => r.data),

  /** 签发预签名下载 URL（仅 succeeded 且未过期） */
  download: (id: string) =>
    apiClient
      .get<ExportDownloadResponse>(`/exports/${id}/download`)
      .then((r) => r.data),

  /** 失败任务重试：按原 filters 新建并入队 */
  retry: (id: string) =>
    apiClient.post<ExportJob>(`/exports/${id}/retry`).then((r) => r.data),
}
