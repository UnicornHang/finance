import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/**
 * shadcn/ui 风格 Button —— 基于 CVA + Radix Slot
 *
 * 变体（沿用项目历史命名，未改为 shadcn 默认 default/destructive 等以保持向后兼容）：
 * - primary      → 默认实色按钮
 * - secondary    → 白底 + 边框
 * - ghost        → 透明，hover 出表面色
 * - link         → 文本链接样式
 * - danger       → 危险主操作
 * - danger-outline → 危险次操作（描边）
 */
const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-body-md font-semibold',
    'transition-colors duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas',
    'disabled:pointer-events-none disabled:opacity-50',
    'select-none',
    '[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  ].join(' '),
  {
    variants: {
      variant: {
        primary: 'bg-primary text-white hover:bg-primary-hover active:bg-primary-active',
        secondary:
          'bg-surface text-ink border border-line hover:bg-canvas hover:border-line-strong',
        ghost: 'bg-transparent text-ink-secondary hover:bg-surface-inset hover:text-ink',
        link: 'bg-transparent text-primary hover:underline underline-offset-4 px-0',
        danger: 'bg-danger text-white hover:bg-danger-hover',
        'danger-outline':
          'bg-surface text-danger border border-danger-border hover:bg-danger-tint',
      },
      size: {
        sm: 'h-8 px-3 text-body-sm',
        md: 'h-9 px-4',
        lg: 'h-10 px-6',
        xl: 'h-12 px-6 text-body-lg',
        icon: 'h-9 w-9 p-0',
        'icon-sm': 'h-8 w-8 p-0',
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
        data-slot="button"
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

export { buttonVariants }