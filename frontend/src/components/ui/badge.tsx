import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Pristine Crisp Fintech 徽章
 * - 完全 pill 形，与矩形数据卡片形成对比
 * - 实色填充 + 1px 同色系边框 + 600 字重文字
 * - 字体 12px / 0.02em letter-spacing
 */
type Tone = 'success' | 'primary' | 'warning' | 'danger' | 'neutral'

const TONE_STYLES: Record<Tone, string> = {
  success: 'bg-success-tint text-success border-success-border',
  primary: 'bg-primary-tint text-primary border-primary-border',
  warning: 'bg-warning-tint text-warning border-warning-border',
  danger: 'bg-danger-tint text-danger border-danger-border',
  neutral: 'bg-canvas text-ink-secondary border-line',
}

const TONE_DOTS: Record<Tone, string> = {
  success: 'bg-success',
  primary: 'bg-primary',
  warning: 'bg-warning',
  danger: 'bg-danger',
  neutral: 'bg-ink-tertiary',
}

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  dot?: boolean
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, tone = 'neutral', dot = false, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5',
        'text-label-md font-semibold',
        TONE_STYLES[tone],
        className,
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn('inline-block h-1.5 w-1.5 rounded-full', TONE_DOTS[tone])}
          aria-hidden
        />
      )}
      {children}
    </span>
  ),
)
Badge.displayName = 'Badge'