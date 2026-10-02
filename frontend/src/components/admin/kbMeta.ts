/** 知识库文档状态样式。 */
export const KB_STATUS_TONE: Record<
  string,
  'success' | 'warning' | 'danger' | 'neutral'
> = {
  active: 'success',
  ready: 'success',
  indexing: 'warning',
  pending: 'neutral',
  failed: 'danger',
}

/** 知识库文档状态文案。 */
export const KB_STATUS_LABEL: Record<string, string> = {
  active: '已就绪',
  ready: '已就绪',
  indexing: '索引中',
  pending: '待索引',
  failed: '失败',
}

/** 知识库文档类型选项。 */
export const KB_DOC_TYPES = [
  { value: 'policy', label: '制度政策' },
  { value: 'rule', label: '合规规则' },
  { value: 'template', label: '合同模板' },
  { value: 'other', label: '其他' },
] as const

/** 将 doc_type 转为展示文案。 */
export function kbDocTypeLabel(docType: string | null | undefined): string {
  if (!docType) return '通用'
  const found = KB_DOC_TYPES.find((t) => t.value === docType)
  return found?.label || docType
}
