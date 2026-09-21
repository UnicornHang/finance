import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cva, type VariantProps } from 'class-variance-authority'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * shadcn/ui 风格 Sheet —— 基于 @radix-ui/react-dialog 的 side 变体
 *
 * 用法：与 Dialog 形态一致，使用 side=top/right/bottom/left 控制弹出方向
 *   <Sheet open={open} onOpenChange={setOpen}>
 *     <SheetContent side="right">
 *       <SheetHeader>
 *         <SheetTitle>标题</SheetTitle>
 *         <SheetDescription>说明</SheetDescription>
 *       </SheetHeader>
 *       ...
 *     </SheetContent>
 *   </Sheet>
 */

export const Sheet = DialogPrimitive.Root
export const SheetTrigger = DialogPrimitive.Trigger
export const SheetClose = DialogPrimitive.Close
export const SheetPortal = DialogPrimitive.Portal

export const SheetOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    data-slot="sheet-overlay"
    className={cn(
      'fixed inset-0 z-50 bg-ink/30',
      'data-[state=open]:animate-in data-[state=closed]:animate-out',
      'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
      className,
    )}
    {...props}
  />
))
SheetOverlay.displayName = 'SheetOverlay'

const sheetVariants = cva(
  [
    'fixed z-50 gap-4 bg-surface shadow-raised',
    'data-[state=open]:animate-in data-[state=closed]:animate-out',
    'transition ease-in-out',
  ].join(' '),
  {
    variants: {
      side: {
        top: 'inset-x-0 top-0 border-b border-line-strong',
        bottom: 'inset-x-0 bottom-0 border-t border-line-strong',
        left: 'inset-y-0 left-0 h-full w-3/4 border-r border-line-strong sm:max-w-sm',
        right:
          'inset-y-0 right-0 h-full w-3/4 border-l border-line-strong sm:max-w-md',
      },
    },
    defaultVariants: { side: 'right' },
  },
)

export interface SheetContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>,
    VariantProps<typeof sheetVariants> {}

export const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  SheetContentProps
>(({ side = 'right', className, children, ...props }, ref) => (
  <SheetPortal>
    <SheetOverlay />
    <DialogPrimitive.Content
      ref={ref}
      data-slot="sheet-content"
      className={cn(sheetVariants({ side }), className)}
      {...props}
    >
      {children}
      <DialogPrimitive.Close
        className={cn(
          'absolute right-4 top-4 rounded-sm text-ink-tertiary',
          'opacity-70 transition-opacity hover:opacity-100',
          'focus:outline-none focus:ring-2 focus:ring-primary/40',
          'disabled:pointer-events-none',
        )}
      >
        <X className="h-4 w-4" />
        <span className="sr-only">关闭</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </SheetPortal>
))
SheetContent.displayName = 'SheetContent'

export function SheetHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="sheet-header"
      className={cn(
        'flex flex-col space-y-1.5 px-5 py-4 border-b border-line-subtle text-left',
        className,
      )}
      {...props}
    />
  )
}

export function SheetFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn(
        'flex flex-col-reverse gap-2 px-5 py-3 border-t border-line-subtle sm:flex-row sm:justify-end',
        className,
      )}
      {...props}
    />
  )
}

export const SheetTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    data-slot="sheet-title"
    className={cn(
      'text-headline-sm font-semibold text-ink tracking-tight',
      className,
    )}
    {...props}
  />
))
SheetTitle.displayName = 'SheetTitle'

export const SheetDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    data-slot="sheet-description"
    className={cn('text-body-sm text-ink-tertiary', className)}
    {...props}
  />
))
SheetDescription.displayName = 'SheetDescription'