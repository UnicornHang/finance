import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * shadcn/ui 风格 Input —— 保留原生 <input> 的同时对齐视觉/焦点行为
 *
 * 配套：
 * - 焦点环：focus-visible:ring-2 focus-visible:ring-primary/40
 * - 失效态：invalid:border-danger + invalid:ring-danger/40
 * - Label 关联：使用 peer-disabled 时由 <Label> 自动灰化
 */

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, invalid, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded-md border border-line bg-surface px-3 py-2 text-body-md text-ink',
        'placeholder:text-ink-muted',
        'transition-all duration-200 ease-smooth',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 focus-visible:border-primary',
        'disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-canvas',
        'file:border-0 file:bg-transparent file:text-sm file:font-medium',
        invalid &&
          'border-danger focus-visible:border-danger focus-visible:ring-danger/20',
        !invalid && 'border-line',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

/**
 * shadcn/ui 风格 Textarea
 */
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'flex min-h-[80px] w-full rounded-md border border-line bg-surface px-3 py-2 text-body-md text-ink',
      'placeholder:text-ink-muted',
      'transition-all duration-200 ease-smooth',
      'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 focus-visible:border-primary',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  />
))
Textarea.displayName = 'Textarea'