import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * 表单字段组合（shadcn 风格 Field 抽象）
 *
 * 兼容既有 <Field label error hint>...</Field> 用法
 * 通过 data-slot="field" 标识供外部识别
 */

export interface FieldProps {
  label: string
  error?: string
  required?: boolean
  hint?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export function Field({
  label,
  error,
  required,
  hint,
  children,
  className,
}: FieldProps) {
  return (
    <div
      data-slot="field"
      className={cn('space-y-1.5', className)}
    >
      <label className="block text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
        {label}
        {required && <span className="ml-1 text-danger normal-case">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="text-body-sm text-ink-tertiary">{hint}</p>
      )}
      {error && <p className="text-body-sm text-danger">{error}</p>}
    </div>
  )
}