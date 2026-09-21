import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * shadcn/ui 风格 Card —— 平面卡片 + hairline 边框
 *
 * 关键属性：
 * - data-slot="card" / "card-header" / "card-title" 等供组合组件识别
 * - 通过 peer 等可与 Label/Input 联动
 */

export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card"
    className={cn(
      'rounded-lg border border-line bg-surface text-ink',
      className,
    )}
    {...props}
  />
))
Card.displayName = 'Card'

export const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-header"
    className={cn(
      'flex flex-col gap-1.5 px-5 py-4 border-b border-line-subtle',
      className,
    )}
    {...props}
  />
))
CardHeader.displayName = 'CardHeader'

export const CardTitle = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-title"
    className={cn(
      'text-headline-sm font-semibold tracking-tight text-ink',
      className,
    )}
    {...props}
  />
))
CardTitle.displayName = 'CardTitle'

export const CardDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-description"
    className={cn('text-body-sm text-ink-tertiary', className)}
    {...props}
  />
))
CardDescription.displayName = 'CardDescription'

/**
 * 卡片右上角的操作区（如按钮组）。与 CardHeader 配合使用，靠右浮起。
 */
export const CardAction = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-action"
    className={cn('flex items-center gap-2 self-start', className)}
    {...props}
  />
))
CardAction.displayName = 'CardAction'

export const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-content"
    className={cn('p-5', className)}
    {...props}
  />
))
CardContent.displayName = 'CardContent'

export const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-footer"
    className={cn(
      'flex items-center justify-between gap-2 px-5 py-3 border-t border-line-subtle',
      className,
    )}
    {...props}
  />
))
CardFooter.displayName = 'CardFooter'