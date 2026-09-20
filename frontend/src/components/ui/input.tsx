import * as React from 'react'
import { cn } from '@/lib/utils'

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

/**
 * Pristine Crisp Fintech 输入控件
 * - 白底 + 1px 边框 + 4px 圆角
 * - 高度 40px，字号 14px
 * - Focus: 边框 primary + 2px primary focus ring
 */
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, invalid, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded border bg-surface px-3 text-body-md text-ink',
        'placeholder:text-ink-muted',
        'transition-colors duration-150',
        'focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30',
        'disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-canvas',
        invalid && 'border-danger focus-visible:border-danger focus-visible:ring-danger/30',
        !invalid && 'border-line',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

/**
 * 多行文本域
 */
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'flex min-h-[80px] w-full rounded border border-line bg-surface px-3 py-2 text-body-md text-ink',
      'placeholder:text-ink-muted',
      'transition-colors duration-150',
      'focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  />
))
Textarea.displayName = 'Textarea'

/**
 * Select
 */
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      'flex h-10 w-full rounded border border-line bg-surface px-3 text-body-md text-ink',
      'transition-colors duration-150',
      'focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  >
    {children}
  </select>
))
Select.displayName = 'Select'

/**
 * Label
 */
export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement> & { required?: boolean }
>(({ className, required, children, ...props }, ref) => (
  <label
    ref={ref}
    className={cn(
      'block text-label-md font-semibold uppercase tracking-wider text-ink-tertiary mb-1.5',
      className,
    )}
    {...props}
  >
    {children}
    {required && <span className="ml-1 text-danger normal-case">*</span>}
  </label>
))
Label.displayName = 'Label'