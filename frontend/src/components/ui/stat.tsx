import * as React from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Pristine Crisp Fintech 财务指标卡 (KPI)
 * - Label: 12px uppercase semibold #64748b
 * - Value: 28px semibold #0f172a, tabular-nums
 * - Delta: 紧凑 pill, 翠绿 on 浅绿底
 */
export interface StatCardProps {
  label: string
  value: React.ReactNode
  suffix?: React.ReactNode
  prefix?: React.ReactNode
  delta?: number
  deltaLabel?: string
  tone?: 'neutral' | 'success' | 'danger'
  icon?: React.ReactNode
  className?: string
  hint?: React.ReactNode
}

export function StatCard({
  label,
  value,
  suffix,
  prefix,
  delta,
  deltaLabel,
  tone = 'neutral',
  icon,
  className,
  hint,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-line bg-surface px-5 py-4',
        'flex flex-col gap-2',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
          {label}
        </span>
        {icon && (
          <div className="flex h-6 w-6 items-center justify-center rounded bg-canvas text-ink-tertiary">
            {icon}
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-1">
        {prefix && (
          <span className="text-body-md text-ink-tertiary">{prefix}</span>
        )}
        <span className="text-numeric-lg font-semibold text-ink tabular-nums">
          {value}
        </span>
        {suffix && (
          <span className="text-body-md text-ink-tertiary">{suffix}</span>
        )}
      </div>

      <div className="flex items-center gap-2 min-h-[20px]">
        {typeof delta === 'number' && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-label-md font-semibold tabular-nums',
              tone === 'success' && 'bg-success-tint text-success border-success-border',
              tone === 'danger' && 'bg-danger-tint text-danger border-danger-border',
              tone === 'neutral' && 'bg-canvas text-ink-secondary border-line',
            )}
          >
            {delta >= 0 ? (
              <ArrowUpRight className="h-3 w-3" />
            ) : (
              <ArrowDownRight className="h-3 w-3" />
            )}
            {Math.abs(delta).toFixed(1)}%
          </span>
        )}
        {deltaLabel && (
          <span className="text-body-sm text-ink-tertiary">{deltaLabel}</span>
        )}
        {hint && !deltaLabel && (
          <span className="text-body-sm text-ink-tertiary">{hint}</span>
        )}
      </div>
    </div>
  )
}

/**
 * 区块标题
 * - title: 蓝色 headline 大标题（统一替代原 eyebrow + title 两段式）
 * - description: 灰色副说明
 * - actions: 右侧操作区（如 "新增" 按钮）
 */
export function SectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string
  description?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-end justify-between gap-4', className)}>
      <div className="min-w-0 space-y-1.5">
        <h1 className="text-headline-lg font-semibold text-primary tracking-tight">
          {title}
        </h1>
        {description && (
          <p className="text-body-md text-ink-tertiary">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}