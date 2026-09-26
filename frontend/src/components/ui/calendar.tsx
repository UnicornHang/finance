import * as React from 'react'
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  DayButton,
  DayPicker,
  getDefaultClassNames,
  type ChevronProps,
} from 'react-day-picker'

import { cn } from '@/lib/utils'
import { Button, buttonVariants, type ButtonProps } from '@/components/ui/button'

/**
 * shadcn/ui 日历。
 * 月份显示为「9月」，年份单独下拉；星期标题保持 Su–Sa，和这套组件的默认外观一致。
 */
export function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  captionLayout = 'dropdown',
  buttonVariant = 'ghost',
  formatters,
  components,
  ...props
}: React.ComponentProps<typeof DayPicker> & {
  buttonVariant?: ButtonProps['variant']
}) {
  const defaultClassNames = getDefaultClassNames()

  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      captionLayout={captionLayout}
      className={cn(
        'bg-surface p-3 [--cell-size:2.25rem]',
        className,
      )}
      formatters={{
        formatMonthDropdown: (date) => `${date.getMonth() + 1}月`,
        ...formatters,
      }}
      classNames={{
        root: cn('w-fit', defaultClassNames.root),
        months: cn('relative flex flex-col', defaultClassNames.months),
        month: cn('flex w-full flex-col gap-3', defaultClassNames.month),
        nav: cn(
          'absolute inset-x-0 top-0 flex w-full items-center justify-between',
          defaultClassNames.nav,
        ),
        button_previous: cn(
          buttonVariants({ variant: buttonVariant }),
          'size-[--cell-size] p-0 text-ink aria-disabled:opacity-40',
          defaultClassNames.button_previous,
        ),
        button_next: cn(
          buttonVariants({ variant: buttonVariant }),
          'size-[--cell-size] p-0 text-ink aria-disabled:opacity-40',
          defaultClassNames.button_next,
        ),
        month_caption: cn(
          'flex h-[--cell-size] w-full items-center justify-center px-[--cell-size]',
          defaultClassNames.month_caption,
        ),
        dropdowns: cn(
          'flex h-[--cell-size] items-center justify-center gap-1.5 text-sm font-medium text-ink',
          defaultClassNames.dropdowns,
        ),
        dropdown_root: cn(
          'relative rounded-md',
          defaultClassNames.dropdown_root,
        ),
        dropdown: cn(
          'absolute inset-0 cursor-pointer opacity-0',
          defaultClassNames.dropdown,
        ),
        caption_label: cn(
          'flex h-8 select-none items-center gap-1 rounded-md px-1 text-sm font-medium text-ink [&>svg]:size-3.5 [&>svg]:text-ink-tertiary',
          defaultClassNames.caption_label,
        ),
        month_grid: cn('w-full border-collapse', defaultClassNames.month_grid),
        weekdays: cn('flex', defaultClassNames.weekdays),
        weekday: cn(
          'flex-1 select-none text-center text-[0.8rem] font-normal text-ink-tertiary',
          defaultClassNames.weekday,
        ),
        week: cn('mt-1 flex w-full', defaultClassNames.week),
        day: cn(
          'group/day relative aspect-square h-full w-full p-0 text-center',
          defaultClassNames.day,
        ),
        today: cn(defaultClassNames.today),
        outside: cn('text-ink-muted', defaultClassNames.outside),
        disabled: cn('text-ink-muted opacity-40', defaultClassNames.disabled),
        hidden: cn('invisible', defaultClassNames.hidden),
        ...classNames,
      }}
      components={{
        Root: ({ className: rootClassName, rootRef, ...rootProps }) => (
          <div
            data-slot="calendar"
            ref={rootRef}
            className={cn(rootClassName)}
            {...rootProps}
          />
        ),
        Chevron: CalendarChevron,
        DayButton: CalendarDayButton,
        ...components,
      }}
      {...props}
    />
  )
}

/** 左右翻月和年月下拉共用的小箭头。 */
function CalendarChevron({ orientation, className, disabled }: ChevronProps) {
  const iconClass = cn('size-4', disabled && 'opacity-40', className)
  if (orientation === 'left') return <ChevronLeft className={iconClass} />
  if (orientation === 'right') return <ChevronRight className={iconClass} />
  return <ChevronDown className={iconClass} />
}

/** 单日按钮：今天是浅灰圆，选中是实心圆。 */
function CalendarDayButton({
  className,
  day,
  modifiers,
  ...props
}: React.ComponentProps<typeof DayButton>) {
  const ref = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    if (modifiers.focused) ref.current?.focus()
  }, [modifiers.focused])

  return (
    <Button
      ref={ref}
      variant="ghost"
      size="icon"
      data-day={day.isoDate}
      data-selected-single={
        modifiers.selected &&
        !modifiers.range_start &&
        !modifiers.range_end &&
        !modifiers.range_middle
      }
      className={cn(
        'aspect-square h-auto w-full min-w-[--cell-size] rounded-full p-0 font-normal text-ink',
        'hover:bg-surface-inset hover:text-ink',
        modifiers.outside && 'text-ink-muted',
        modifiers.today && !modifiers.selected && 'bg-surface-inset',
        modifiers.selected && 'bg-ink text-white hover:bg-ink hover:text-white',
        className,
      )}
      {...props}
    />
  )
}

export { CalendarDayButton }
