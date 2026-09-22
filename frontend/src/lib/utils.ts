import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(d: Date | string | null | undefined): string {
  if (!d) return '-'
  const date = typeof d === 'string' ? new Date(d) : d
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 将日期按 DeepSeek 风格分组到时间桶。
 *  - 今天  → 当天 0:00 之后
 *  - 7天内 → 过去 7 天
 *  - 30天内 → 过去 30 天
 *  - 其余  → YYYY-MM（按月分组）
 */
export type DateBucket = 'today' | '7days' | '30days' | 'older'

export function getDateBucket(d: Date | string | null | undefined): {
  bucket: DateBucket
  /** older 分组时携带 YYYY-MM，否则为空串 */
  monthKey: string
  /** 列表渲染时用的展示标题 */
  label: string
} {
  if (!d) return { bucket: '30days', monthKey: '', label: '30天内' }
  const date = typeof d === 'string' ? new Date(d) : d
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diffMs = startOfToday.getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays <= 0) return { bucket: 'today', monthKey: '', label: '今天' }
  if (diffDays < 7) return { bucket: '7days', monthKey: '', label: '7天内' }
  if (diffDays < 30) return { bucket: '30days', monthKey: '', label: '30天内' }
  const yyyy = date.getFullYear().toString().padStart(4, '0')
  const mm = (date.getMonth() + 1).toString().padStart(2, '0')
  return { bucket: 'older', monthKey: `${yyyy}-${mm}`, label: `${yyyy}-${mm}` }
}

export function formatCurrency(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
  }).format(n)
}