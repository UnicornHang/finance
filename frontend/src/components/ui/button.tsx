import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/**
 * Pristine Crisp Fintech 按钮
 * - 平面实色 + hairline 边框，禁止重投影
 * - 圆角 4px（控件级精度）
 * - 字号 14px / weight 600
 */
const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap',
    'rounded text-body-md font-semibold',
    'transition-colors duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-0',
    'disabled:pointer-events-none disabled:opacity-50',
    'select-none',
  ].join(' '),
  {
    variants: {
      variant: {
        // Primary 实色填充
        primary: 'bg-primary text-white hover:bg-primary-hover active:bg-primary-active',
        // Secondary 白底 + hairline 边框
        secondary:
          'bg-surface text-ink border border-line hover:bg-canvas hover:border-line-strong',
        // Ghost - 仅文字，hover 出表面色
        ghost: 'bg-transparent text-ink-secondary hover:bg-surface-inset hover:text-ink',
        // Tertiary - 透明无边
        link: 'bg-transparent text-primary hover:underline underline-offset-4 px-0',
        // Destructive
        danger: 'bg-danger text-white hover:bg-danger-hover',
        // Outline danger
        'danger-outline':
          'bg-surface text-danger border border-danger-border hover:bg-danger-tint',
      },
      size: {
        sm: 'h-8 px-3 text-body-sm',
        md: 'h-9 px-4',
        lg: 'h-11 px-6 text-body-lg',
        xl: 'h-12 px-6 text-body-lg',
        icon: 'h-9 w-9',
        'icon-sm': 'h-8 w-8',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

export { buttonVariants }