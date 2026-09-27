/** 发票类型在列表、导出和详情里共用的文案。 */
export const TYPE_LABEL: Record<string, string> = {
  special: '专票',
  general: '普票',
  electronic: '电子发票',
  vehicle: '机动车销售发票',
}

export const TYPE_TONE: Record<string, 'primary' | 'success' | 'neutral'> = {
  special: 'primary',
  general: 'success',
  electronic: 'neutral',
  vehicle: 'primary',
}

/** 归档状态文案。 */
export const STATUS_LABEL: Record<string, string> = {
  pending_review: '待确认',
  active: '已归档',
  deleted: '已删除',
}

export const STATUS_TONE: Record<string, 'primary' | 'success' | 'neutral' | 'warning'> = {
  pending_review: 'warning',
  active: 'success',
  deleted: 'neutral',
}
