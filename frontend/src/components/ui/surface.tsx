import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Pristine Crisp Fintech 侧滑面板 (Side Panel)
 * - 屏幕右侧滑入 (500px 默认)
 * - 白底 + 1px 边框 + 仅留精确边缘阴影 (raised)
 * - 用于发票/合同识别结果的确认与归档
 */
export interface SidePanelProps {
  open: boolean
  onClose: () => void
  title: React.ReactNode
  subtitle?: React.ReactNode
  icon?: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  width?: number | string
}

export function SidePanel({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  width = 500,
}: SidePanelProps) {
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 背景遮罩 — 仅极轻 (非模糊) */}
      <div
        className="absolute inset-0 bg-ink/5 animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden
      />
      {/* 面板本体 */}
      <div
        className={cn(
          'relative h-full bg-surface border-l border-line-strong shadow-raised',
          'flex flex-col animate-in slide-in-from-right duration-200',
        )}
        style={{ width: typeof width === 'number' ? `${width}px` : width }}
      >
        {/* Header */}
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-line-subtle shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            {icon && (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-primary-tint text-primary">
                {icon}
              </div>
            )}
            <div className="min-w-0">
              <h2 className="text-headline-sm font-semibold text-ink truncate">
                {title}
              </h2>
              {subtitle && (
                <p className="text-body-sm text-ink-tertiary truncate">
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-ink-tertiary hover:bg-surface-inset hover:text-ink transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>

        {/* Footer */}
        {footer && (
          <footer className="flex items-center justify-end gap-2 px-5 py-3 border-t border-line-subtle shrink-0 bg-canvas">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )
}

/**
 * 字段组件 (Form Field)
 */
export function Field({
  label,
  error,
  required,
  hint,
  children,
}: {
  label: string
  error?: string
  required?: boolean
  hint?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
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