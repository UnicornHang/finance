import { apiClient } from './client'
import type { AuditLogListResponse, AuditLogMeta } from '@/types'

/** 审计日志筛选。空字段不传给后端。 */
export interface AuditLogQuery {
  page?: number
  page_size?: number
  user_id?: string
  operation_type?: string
  start_date?: string
  end_date?: string
}

function toParams(query: AuditLogQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  if (query.page) params.page = query.page
  if (query.page_size) params.page_size = query.page_size
  if (query.user_id) params.user_id = query.user_id
  if (query.operation_type) params.operation_type = query.operation_type
  if (query.start_date) params.start_date = query.start_date
  if (query.end_date) params.end_date = query.end_date
  return params
}

export const auditApi = {
  /** 筛选项：操作类型、本租户用户 */
  meta: () => apiClient.get<AuditLogMeta>('/audit-logs/meta').then((r) => r.data),

  /** 分页列表 */
  list: (query: AuditLogQuery) =>
    apiClient
      .get<AuditLogListResponse>('/audit-logs/', { params: toParams(query) })
      .then((r) => r.data),

  /** 管理员导出当前筛选结果 */
  exportExcel: (query: AuditLogQuery) =>
    apiClient
      .get<Blob>('/audit-logs/export', {
        params: toParams(query),
        responseType: 'blob',
      })
      .then((r) => r.data),
}
