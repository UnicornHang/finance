import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/**
 * shadcn/ui 风格 Badge —— CVA 变体 + dot 后缀
 *
 * 变体：
 * - tone: success / primary / warning / danger / neutral / outline
 * - shape: pill（默认）/ square
 */

export const badgeVariants = cva(
  [
    'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5',
    'text-label-md font-semibold',
    'transition-colors',
  ].join(' '),
  {
    variants: {
      tone: {
        success: 'bg-success-tint text-success border-success-border',
        primary: 'bg-primary-tint text-primary border-primary-border',
        warning: 'bg-warning-tint text-warning border-warning-border',
        danger: 'bg-danger-tint text-danger border-danger-border',
        neutral: 'bg-canvas text-ink-secondary border-line',
        outline: 'bg-transparent text-ink-secondary border-line',
      },
      shape: {
        pill: 'rounded-full',
        square: 'rounded-md',
      },
    },
    defaultVariants: { tone: 'neutral', shape: 'pill' },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, tone, shape, dot = false, children, ...props }, ref) => {
    const dotClass = cn(
      'inline-block h-1.5 w-1.5 rounded-full',
      tone === 'success' && 'bg-success',
      tone === 'primary' && 'bg-primary',
      tone === 'warning' && 'bg-warning',
      tone === 'danger' && 'bg-danger',
      (tone === 'neutral' || tone === 'outline' || !tone) && 'bg-ink-tertiary',
    )
    return (
      <span
        ref={ref}
        data-slot="badge"
        className={cn(badgeVariants({ tone, shape }), className)}
        {...props}
      >
        {dot && <span className={dotClass} aria-hidden />}
        {children}
      </span>
    )
  },
)
Badge.displayName = 'Badge'

export { badgeVariants as _badgeVariants }