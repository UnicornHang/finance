import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const PAGE_SIZE_OPTIONS = [5,10, 20, 50] as const

/**
 * 页码窗口。页数不多时全部列出；变多后只保留首页、尾页和当前页两侧，中间用省略号。
 */
function buildPageItems(current: number, totalPages: number): Array<number | 'ellipsis'> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const nearby = [1, totalPages, current - 1, current, current + 1].filter(
    (page) => page >= 1 && page <= totalPages,
  )
  const unique = [...new Set(nearby)].sort((a, b) => a - b)
  const items: Array<number | 'ellipsis'> = []
  unique.forEach((page, index) => {
    if (index > 0 && page - unique[index - 1] > 1) items.push('ellipsis')
    items.push(page)
  })
  return items
}

export interface InvoiceListPagerProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

/** 发票列表底部分页：条数范围、每页条数、页码。 */
export function InvoiceListPager({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: InvoiceListPagerProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  const items = buildPageItems(page, totalPages)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-subtle px-4 py-3">
      <span className="text-body-sm tabular-nums text-ink-tertiary">
        {total === 0 ? '共 0 条' : `第 ${from}-${to} 条，共 ${total} 条`}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-body-sm text-ink-tertiary">每页</span>
        <Select
          value={String(pageSize)}
          onValueChange={(value) => onPageSizeChange(Number(value))}
        >
          <SelectTrigger className="h-8 w-[4.5rem]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="secondary"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="上一页"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        {items.map((item, index) =>
          item === 'ellipsis' ? (
            <span key={`ellipsis-${index}`} className="px-1 text-body-sm text-ink-muted">
              …
            </span>
          ) : (
            <Button
              key={item}
              variant={item === page ? 'primary' : 'secondary'}
              size="sm"
              className={
                item === page
                  ? 'min-w-8 bg-primary px-2 !text-white hover:bg-primary-hover hover:!text-white'
                  : 'min-w-8 px-2'
              }
              onClick={() => onPageChange(item)}
            >
              {item}
            </Button>
          ),
        )}
        <Button
          variant="secondary"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="下一页"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
