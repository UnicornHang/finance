import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, ScrollText } from 'lucide-react'
import { toast } from 'sonner'

import { auditApi, type AuditLogQuery } from '@/api/audit'
import { InvoiceListPager } from '@/components/admin/InvoiceListPager'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { SectionHeader } from '@/components/ui/stat'
import { EmptyState, Table, TBody, TD, TH, THead, Toolbar, TR } from '@/components/ui/table'
import { apiErrorMessage, formatDate } from '@/lib/utils'
import type { AuditLogItem } from '@/types'

const DEFAULT_PAGE_SIZE = 20

/** 把 blob 错误体还原成后端 message。 */
async function blobErrorMessage(error: unknown, fallback: string): Promise<string> {
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (data instanceof Blob) {
    try {
      const text = await data.text()
      const parsed = JSON.parse(text) as { message?: string; detail?: string }
      if (parsed.message) return parsed.message
      if (typeof parsed.detail === 'string') return parsed.detail
    } catch {
      return fallback
    }
  }
  return apiErrorMessage(error, fallback)
}

/** 触发浏览器下载。 */
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** 快照格式化，空对象显示为无。 */
function formatSnapshot(value: Record<string, unknown> | null): string {
  if (!value || Object.keys(value).length === 0) return '无'
  return JSON.stringify(value, null, 2)
}

/** 后台审计日志：仅管理员可进入，按时间、用户、操作类型筛选并导出。 */
export function AuditLogs() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [userId, setUserId] = useState('all')
  const [operationType, setOperationType] = useState('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [detail, setDetail] = useState<AuditLogItem | null>(null)

  const filters: AuditLogQuery = {
    page,
    page_size: pageSize,
    user_id: userId === 'all' ? undefined : userId,
    operation_type: operationType === 'all' ? undefined : operationType,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
  }

  const metaQuery = useQuery({
    queryKey: ['audit-logs', 'meta'],
    queryFn: () => auditApi.meta(),
  })

  const listQuery = useQuery({
    queryKey: ['audit-logs', filters],
    queryFn: () => auditApi.list(filters),
  })

  const exportMutation = useMutation({
    mutationFn: () =>
      auditApi.exportExcel({
        user_id: filters.user_id,
        operation_type: filters.operation_type,
        start_date: filters.start_date,
        end_date: filters.end_date,
      }),
    onSuccess: (blob) => {
      saveBlob(blob, '审计日志.xlsx')
      toast.success('已开始下载')
    },
    onError: async (error) => {
      toast.error(await blobErrorMessage(error, '导出失败'))
    },
  })

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  /** 改筛选时回到第一页。 */
  const resetPage = () => setPage(1)

  return (
    <div className="space-y-6">
      <SectionHeader
        title="审计日志"
        description="保留最近一年。记录只追加，不能修改或删除。"
        actions={
          <Button
            size="md"
            variant="secondary"
            disabled={exportMutation.isPending}
            onClick={() => exportMutation.mutate()}
          >
            <Download className="h-4 w-4" />
            导出 Excel
          </Button>
        }
      />

      <Card>
        <Toolbar className="flex-wrap">
          <Select
            value={operationType}
            onValueChange={(value) => {
              setOperationType(value)
              resetPage()
            }}
          >
            <SelectTrigger className="h-9 w-44">
              <SelectValue placeholder="全部操作" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部操作</SelectItem>
              {(metaQuery.data?.operations ?? []).map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={userId}
            onValueChange={(value) => {
              setUserId(value)
              resetPage()
            }}
          >
            <SelectTrigger className="h-9 w-44">
              <SelectValue placeholder="全部用户" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部用户</SelectItem>
              {(metaQuery.data?.users ?? []).map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="w-40">
            <DatePicker
              value={startDate}
              placeholder="开始日期"
              onChange={(value) => {
                setStartDate(value)
                resetPage()
              }}
            />
          </div>
          <div className="w-40">
            <DatePicker
              value={endDate}
              placeholder="结束日期"
              onChange={(value) => {
                setEndDate(value)
                resetPage()
              }}
            />
          </div>
          {(startDate || endDate) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setStartDate('')
                setEndDate('')
                resetPage()
              }}
            >
              清空日期
            </Button>
          )}
        </Toolbar>

        {listQuery.isLoading ? (
          <p className="px-4 py-10 text-center text-body-md text-ink-tertiary">加载中…</p>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<ScrollText className="h-5 w-5" />}
            title="没有审计记录"
            description="当前筛选条件下，最近一年内没有操作记录。"
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>时间</TH>
                <TH>操作人</TH>
                <TH>操作</TH>
                <TH>结果</TH>
                <TH>摘要</TH>
                <TH>IP</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((row) => (
                <TR key={row.id}>
                  <TD className="whitespace-nowrap tabular-nums">
                    {formatDate(row.created_at)}
                  </TD>
                  <TD>
                    <div className="font-medium">{row.user_name || '—'}</div>
                    <div className="text-label-sm text-ink-tertiary">{row.user_account}</div>
                  </TD>
                  <TD>{row.operation_label}</TD>
                  <TD>
                    <Badge tone={row.result === 'failure' ? 'danger' : 'success'}>
                      {row.result === 'failure' ? '失败' : '成功'}
                    </Badge>
                  </TD>
                  <TD className="max-w-[240px] truncate">{row.summary || '—'}</TD>
                  <TD className="whitespace-nowrap tabular-nums">{row.ip || '—'}</TD>
                  <TD>
                    <Button variant="ghost" size="sm" onClick={() => setDetail(row)}>
                      详情
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        <InvoiceListPager
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      </Card>

      <Dialog open={detail !== null} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="w-[min(1200px,92vw)] !max-w-none !overflow-hidden">
          <DialogHeader>
            <DialogTitle>{detail?.operation_label}</DialogTitle>
            <DialogDescription>
              {detail?.user_name || '未知用户'} · {formatDate(detail?.created_at)}
            </DialogDescription>
          </DialogHeader>
          <div className="flex min-w-0 flex-col gap-4">
            <SnapshotBlock title="变更前" value={formatSnapshot(detail?.before_value ?? null)} />
            <SnapshotBlock title="变更后" value={formatSnapshot(detail?.after_value ?? null)} />
          </div>
          {detail?.error_message && (
            <p className="text-body-sm text-danger">失败原因：{detail.error_message}</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** 详情里的 JSON 快照块。 */
function SnapshotBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 text-label-sm font-semibold text-ink-tertiary">{title}</p>
      <pre className="overflow-x-auto overflow-y-hidden whitespace-pre rounded-md bg-canvas p-3 text-body-sm text-ink">
        {value}
      </pre>
    </div>
  )
}
