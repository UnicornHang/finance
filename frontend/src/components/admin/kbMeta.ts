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

/** 切分策略卡片（与后端 catalog 对齐，供上传弹窗离线回退）。 */
export const CHUNK_STRATEGY_CARDS = [
  {
    value: 'parent_child',
    label: '精确查找条款',
    recommended: true,
    suited: '报销、差旅、审批等制度问答',
    how: '先聚合长父块，再切成短子块用于检索；命中子块后用父块回答。',
    example: '检索命中「住宿上限」子块 → 注入包含前后条款的父块',
    cost_hint: '存储略多，检索更准',
    visual: ['短块检索', '长块回答'],
  },
  {
    value: 'structure',
    label: '按章节标题切开',
    recommended: false,
    suited: '带标题的 Markdown / Word 制度',
    how: '读取 Word 标题样式、Markdown 标题和章节编号；每个标题强制从新块开始。',
    example: '# 差旅 → 一块；## 住宿 → 另一块',
    cost_hint: '不额外调用模型',
    visual: ['标题A', '标题B', '标题C'],
  },
  {
    value: 'recursive',
    label: '按段落长度切开',
    recommended: false,
    suited: '没有标题的纯文本、通知、纪要',
    how: '能放进一段就合并，放不下就切开；相邻两块留一点重叠，减少一句话被劈开。',
    example: '三段短通知合成一块；超长附件再按字数切开',
    cost_hint: '最快、最省',
    visual: ['段1+段2', '段3+重叠'],
  },
  {
    value: 'semantic',
    label: '按话题变化切开',
    recommended: false,
    suited: '标题不全、东一句西一句的长文',
    how: '计算相邻句向量距离，在话题距离峰值处断开；失败会明确标记降级。',
    example: '前面都在讲住宿标准，后面改讲合同盖章 → 自动分成两块',
    cost_hint: '索引更慢，会多用一次 Embedding',
    visual: ['同一话题', '话题跳变', '新块'],
  },
] as const

export type ChunkStrategyValue = (typeof CHUNK_STRATEGY_CARDS)[number]['value']

/** 策略展示名。 */
export function chunkStrategyLabel(value: string | null | undefined): string {
  if (!value) return '—'
  const found = CHUNK_STRATEGY_CARDS.find((s) => s.value === value)
  return found?.label || value
}

/** 将 doc_type 转为展示文案。 */
export function kbDocTypeLabel(docType: string | null | undefined): string {
  if (!docType) return '通用'
  const found = KB_DOC_TYPES.find((t) => t.value === docType)
  return found?.label || docType
}
