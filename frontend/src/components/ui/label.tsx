import * as React from 'react'
import * as LabelPrimitive from '@radix-ui/react-label'

import { cn } from '@/lib/utils'

/**
 * shadcn/ui Label —— 基于 @radix-ui/react-label
 *
 * 与原生 <label> 不同：
 * - 通过 Radix 自动关联 peer 输入（Input 需标记 peer-disabled class）
 * - 暴露 data-slot="label" 供组合组件识别
 */

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> & { required?: boolean }
>(({ className, required, children, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(
      'block text-label-md font-semibold uppercase tracking-wider text-ink-tertiary mb-1.5',
      'peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
      className,
    )}
    {...props}
  >
    {children}
    {required && <span className="ml-1 text-danger normal-case">*</span>}
  </LabelPrimitive.Root>
))
Label.displayName = LabelPrimitive.Root.displayName