import { useState } from 'react'
import { Calendar as CalendarIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

/** 表单里的日期是 YYYY-MM-DD，按本地日历日解析，避免时区把日期拨到前一天。 */
function parseISODate(value: string | undefined): Date | undefined {
  if (!value) return undefined
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return undefined
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
}

/** 选中的日期写回 YYYY-MM-DD，和发票字段一致。 */
function formatISODate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** 输入框里显示 2024/03/05，和原来的日期栏一致。 */
function formatDisplayDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}/${month}/${day}`
}

export interface DatePickerProps {
  value?: string
  onChange?: (value: string) => void
  placeholder?: string
  disabled?: boolean
  id?: string
}

/**
 * 日期选择器。点开后是 shadcn Calendar，不再使用浏览器原生日期框。
 */
export function DatePicker({
  value,
  onChange,
  placeholder = '选择日期',
  disabled,
  id,
}: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const selected = parseISODate(value)
  const thisYear = new Date().getFullYear()

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="secondary"
          disabled={disabled}
          className={cn(
            'h-10 w-full justify-between px-3 font-normal hover:bg-surface',
            !selected && 'text-ink-muted',
          )}
        >
          {selected ? formatDisplayDate(selected) : placeholder}
          <CalendarIcon className="text-ink-tertiary" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          captionLayout="dropdown"
          startMonth={new Date(2000, 0)}
          endMonth={new Date(thisYear + 5, 11)}
          onSelect={(date) => {
            if (!date) return
            onChange?.(formatISODate(date))
            setOpen(false)
          }}
        />
      </PopoverContent>
    </Popover>
  )
}
