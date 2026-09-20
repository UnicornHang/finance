import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Pristine Crisp Fintech 数据表格
 * - Header Cell: 36px 高, bg-canvas, 11px uppercase, semibold, #64748b
 * - Body Cell: 48px 高, bg-white, 13/14px #0f172a, tabular-nums
 * - Row Hover: bg-canvas
 * - 分隔线: 1px #f1f5f9
 */
export const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="w-full overflow-x-auto">
      <table
        ref={ref}
        className={cn('w-full border-collapse text-left', className)}
        {...props}
      />
    </div>
  ),
)
Table.displayName = 'Table'

export const THead = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead
      ref={ref}
      className={cn(
        'bg-canvas border-b border-line text-label-sm font-semibold uppercase tracking-wider text-ink-tertiary',
        className,
      )}
      {...props}
    />
  ),
)
THead.displayName = 'THead'

export const TBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <tbody ref={ref} className={cn(className)} {...props} />,
)
TBody.displayName = 'TBody'

export const TR = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn('border-b border-line-subtle transition-colors hover:bg-canvas', className)}
      {...props}
    />
  ),
)
TR.displayName = 'TR'

export const TH = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn('h-9 px-4 align-middle font-semibold uppercase tracking-wider', className)}
      {...props}
    />
  ),
)
TH.displayName = 'TH'

export const TD = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td
      ref={ref}
      className={cn('h-12 px-4 align-middle text-body-md text-ink', className)}
      {...props}
    />
  ),
)
TD.displayName = 'TD'

/**
 * 空状态
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      {icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-canvas text-ink-tertiary">
          {icon}
        </div>
      )}
      <div className="space-y-1">
        <p className="text-title-lg font-semibold text-ink">{title}</p>
        {description && (
          <p className="text-body-md text-ink-tertiary max-w-sm">{description}</p>
        )}
      </div>
      {action}
    </div>
  )
}

/**
 * 工具栏 (Toolbar)
 */
export function Toolbar({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 px-4 py-3 border-b border-line-subtle bg-surface',
        className,
      )}
    >
      {children}
    </div>
  )
}