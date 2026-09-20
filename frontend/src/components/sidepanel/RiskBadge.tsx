import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface Props {
  level: 'high' | 'medium' | 'low' | string | null | undefined
  size?: 'sm' | 'md'
}

const TONE_MAP: Record<string, 'danger' | 'warning' | 'success'> = {
  high: 'danger',
  medium: 'warning',
  low: 'success',
}

const LABEL_MAP: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
}

/**
 * 风险等级徽章 - 与 SystemColor 状态徽章规范完全一致
 */
export function RiskBadge({ level, size = 'md' }: Props) {
  const safe = (level as keyof typeof TONE_MAP) || 'low'
  const tone = TONE_MAP[safe] || 'success'
  return (
    <Badge tone={tone} dot className={cn(size === 'sm' && 'text-label-sm px-2 py-0')}>
      {LABEL_MAP[safe] || '未知'}
    </Badge>
  )
}