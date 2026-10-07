import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, RefreshCw, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'

import { exportApi } from '@/api/export'
import { InvoiceListPager } from '@/components/admin/InvoiceListPager'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { readApiMessage } from '@/lib/apiError'
import { cn, formatDate } from '@/lib/utils'
import type { ExportJob, ExportJobStatus, ExportResourceType } from '@/types'

/** 资源类型筛选：全部 / 发票 / 合同 */
type ResourceFilter = ExportResourceType | 'all'

const DEFAULT_PAGE_SIZE = 10

export interface ExportCenterProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 打开后高亮的任务 id（如刚创建的） */
  highlightId?: string | null
  /** 初始资源类型筛选 */
  defaultResourceType?: ResourceFilter
}

const STATUS_LABEL: Record<ExportJobStatus, string> = {
  queued: '排队中',
  running: '进行中',
  succeeded: '已完成',
  failed: '失败',
  expired: '已过期',
}

const STATUS_TONE: Record<
  ExportJobStatus,
  'neutral' | 'primary' | 'success' | 'danger' | 'warning'
> = {
  queued: 'neutral',
  running: 'primary',
  succeeded: 'success',
  failed: 'danger',
  expired: 'warning',
}

const RESOURCE_LABEL: Record<ExportResourceType, string> = {
  invoice: '发票',
  contract: '合同',
}

/** 是否仍有进行中任务（用于决定是否轮询） */
function hasInflightJobs(items: ExportJob[] | undefined): boolean {
  if (!items?.length) return false
  return items.some((j) => j.status === 'queued' || j.status === 'running')
}

/** 行数/份数展示 */
function formatRowCount(job: ExportJob): string {
  if (job.row_count == null) return '—'
  if (job.resource_type === 'contract') return `${job.row_count} 份`
  return `${job.row_count} 行`
}

/** 按任务状态映射进度条展示（后端暂无百分比，用阶段进度） */
function progressForStatus(status: ExportJobStatus): {
  value: number
  indeterminate: boolean
  label: string
  barClass: string
} {
  switch (status) {
    case 'queued':
      return {
        value: 20,
        indeterminate: false,
        label: '排队中',
        barClass: 'bg-ink-tertiary',
      }
    case 'running':
      return {
        value: 65,
        indeterminate: true,
        label: '导出中',
        barClass: 'bg-primary',
      }
    case 'succeeded':
      return {
        value: 100,
        indeterminate: false,
        label: '已完成',
        barClass: 'bg-success',
      }
    case 'failed':
      return {
        value: 100,
        indeterminate: false,
        label: '失败',
        barClass: 'bg-danger',
      }
    case 'expired':
      return {
        value: 100,
        indeterminate: false,
        label: '已过期',
        barClass: 'bg-ink-tertiary',
      }
    default: {
      const _exhaustive: never = status
      return {
        value: 0,
        indeterminate: false,
        label: String(_exhaustive),
        barClass: 'bg-ink-tertiary',
      }
    }
  }
}

/** 通过临时 <a> 触发下载（弹窗被拦时的兜底） */
function openDownloadUrl(url: string): void {
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) return
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.target = '_blank'
  anchor.rel = 'noopener noreferrer'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
}

/**
 * 导出中心弹窗：分页列表 + 任务进度条，支持筛选、轮询、下载与失败重试。
 */
export function ExportCenter({
  open,
  onOpenChange,
  highlightId = null,
  defaultResourceType = 'all',
}: ExportCenterProps) {
  const queryClient = useQueryClient()
  const [resourceFilter, setResourceFilter] = useState<ResourceFilter>(defaultResourceType)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const highlightRef = useRef<HTMLTableRowElement | null>(null)

  // 打开时同步默认筛选并回到第一页
  useEffect(() => {
    if (!open) return
    setResourceFilter(defaultResourceType)
    setPage(1)
  }, [open, defaultResourceType])

  // 切换类型时回到第一页
  useEffect(() => {
    setPage(1)
  }, [resourceFilter])

  const listQuery = useQuery({
    queryKey: ['exports', resourceFilter, page, pageSize],
    queryFn: () =>
      exportApi.list({
        resource_type: resourceFilter === 'all' ? undefined : resourceFilter,
        page,
        page_size: pageSize,
      }),
    enabled: open,
    refetchInterval: (query) =>
      hasInflightJobs(query.state.data?.items) ? 3000 : false,
  })

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0
  const inflightCount = items.filter(
    (j) => j.status === 'queued' || j.status === 'running',
  ).length

  // 高亮任务滚入可视区
  useEffect(() => {
    if (!open || !highlightId || !highlightRef.current) return
    highlightRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [open, highlightId, items])

  const downloadMutation = useMutation({
    mutationFn: (id: string) => exportApi.download(id),
    onSuccess: (data) => {
      openDownloadUrl(data.url)
    },
    onError: (err) => {
      toast.error(readApiMessage(err) || '下载失败')
    },
  })

  const retryMutation = useMutation({
    mutationFn: (id: string) => exportApi.retry(id),
    onSuccess: (job) => {
      if (job.deduplicated) {
        toast.info(job.message || '已有相同导出任务')
      } else {
        toast.success('已重新排队导出')
      }
      void queryClient.invalidateQueries({ queryKey: ['exports'] })
    },
    onError: (err) => {
      toast.error(readApiMessage(err) || '重试失败')
    },
  })

  const busyId =
    downloadMutation.isPending && downloadMutation.variables
      ? downloadMutation.variables
      : retryMutation.isPending && retryMutation.variables
        ? retryMutation.variables
        : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-4xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b border-line-subtle px-6 py-4 pr-12">
          <DialogTitle>导出记录</DialogTitle>
          <DialogDescription>查看导出进度、下载文件或重试失败任务</DialogDescription>
        </DialogHeader>

        <div className="flex shrink-0 items-center gap-2 border-b border-line-subtle px-6 py-3">
          <Select
            value={resourceFilter}
            onValueChange={(v) => setResourceFilter(v as ResourceFilter)}
          >
            <SelectTrigger className="h-9 w-36">
              <SelectValue placeholder="全部类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="invoice">发票</SelectItem>
              <SelectItem value="contract">合同</SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="刷新列表"
            disabled={listQuery.isFetching}
            onClick={() => void listQuery.refetch()}
          >
            <RefreshCw className={cn('h-4 w-4', listQuery.isFetching && 'animate-spin')} />
          </Button>
          {inflightCount > 0 && (
            <span className="ml-auto text-body-sm text-ink-secondary">
              当前页 {inflightCount} 个任务进行中
            </span>
          )}
        </div>

        {/* 有进行中任务时展示顶部总览进度条 */}
        {inflightCount > 0 && (
          <div className="shrink-0 border-b border-line-subtle bg-primary-tint/30 px-6 py-3">
            <div className="mb-1.5 flex items-center justify-between text-label-sm text-ink-secondary">
              <span>导出进行中</span>
              <span>自动刷新中…</span>
            </div>
            <ExportProgressBar indeterminate barClass="bg-primary" value={60} />
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {listQuery.isLoading ? (
            <div className="flex items-center justify-center py-16 text-ink-tertiary">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : listQuery.isError ? (
            <div className="py-12 text-center text-body-sm text-danger">
              {readApiMessage(listQuery.error) || '加载导出任务失败'}
            </div>
          ) : items.length === 0 ? (
            <div className="py-12 text-center text-body-sm text-ink-tertiary">暂无导出记录</div>
          ) : (
            <table className="w-full text-left text-body-sm">
              <thead className="sticky top-0 z-10 border-b border-line-subtle bg-surface">
                <tr className="text-label-sm text-ink-tertiary">
                  <th className="px-6 py-2.5 font-medium">类型</th>
                  <th className="px-3 py-2.5 font-medium">状态</th>
                  <th className="min-w-[8rem] px-3 py-2.5 font-medium">进度</th>
                  <th className="px-3 py-2.5 font-medium">数量</th>
                  <th className="px-3 py-2.5 font-medium">创建时间</th>
                  <th className="px-6 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((job) => {
                  const highlighted = highlightId === job.id
                  return (
                    <tr
                      key={job.id}
                      ref={highlighted ? highlightRef : undefined}
                      className={cn(
                        'border-b border-line-subtle align-top',
                        highlighted && 'bg-primary-tint/40',
                      )}
                    >
                      <ExportJobRow
                        job={job}
                        busy={busyId === job.id}
                        downloading={
                          downloadMutation.isPending && downloadMutation.variables === job.id
                        }
                        retrying={retryMutation.isPending && retryMutation.variables === job.id}
                        onDownload={() => downloadMutation.mutate(job.id)}
                        onRetry={() => retryMutation.mutate(job.id)}
                      />
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {!(listQuery.isLoading && !listQuery.data) && (
          <div className="shrink-0">
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
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

interface ExportProgressBarProps {
  value: number
  indeterminate?: boolean
  barClass: string
}

/** 导出进度条：确定进度或进行中不确定动画 */
function ExportProgressBar({ value, indeterminate = false, barClass }: ExportProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-inset"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : clamped}
    >
      {indeterminate ? (
        <div className="relative h-full w-full overflow-hidden">
          <div
            className={cn('absolute inset-y-0 w-1/3 rounded-full', barClass)}
            style={{ animation: 'export-progress-slide 1.2s ease-in-out infinite' }}
          />
        </div>
      ) : (
        <div
          className={cn('h-full rounded-full transition-[width] duration-300', barClass)}
          style={{ width: `${clamped}%` }}
        />
      )}
    </div>
  )
}

interface ExportJobRowProps {
  job: ExportJob
  busy: boolean
  downloading: boolean
  retrying: boolean
  onDownload: () => void
  onRetry: () => void
}

/** 单条导出任务（表格行内容） */
function ExportJobRow({
  job,
  busy,
  downloading,
  retrying,
  onDownload,
  onRetry,
}: ExportJobRowProps) {
  const status = job.status as ExportJobStatus
  const canDownload = status === 'succeeded'
  const canRetry = status === 'failed'
  const progress = progressForStatus(status)

  return (
    <>
      <td className="px-6 py-3">
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-ink">
            {RESOURCE_LABEL[job.resource_type] ?? job.resource_type}
          </span>
          <span className="text-label-sm text-ink-tertiary">
            {job.artifact_kind === 'zip' ? 'ZIP' : 'Excel'}
          </span>
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="space-y-1">
          <Badge tone={STATUS_TONE[status] ?? 'neutral'} shape="square">
            {STATUS_LABEL[status] ?? status}
          </Badge>
          {job.error_message && (status === 'failed' || status === 'expired') && (
            <p className="max-w-[8rem] text-label-sm text-danger line-clamp-2" title={job.error_message}>
              {job.error_message}
            </p>
          )}
        </div>
      </td>
      <td className="min-w-[8rem] px-3 py-3">
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2 text-label-sm text-ink-tertiary">
            <span>{progress.label}</span>
            {!progress.indeterminate && <span className="tabular-nums">{progress.value}%</span>}
          </div>
          <ExportProgressBar
            value={progress.value}
            indeterminate={progress.indeterminate}
            barClass={progress.barClass}
          />
          {job.file_name && status === 'succeeded' && (
            <p className="truncate text-label-sm text-ink-tertiary" title={job.file_name}>
              {job.file_name}
            </p>
          )}
        </div>
      </td>
      <td className="whitespace-nowrap px-3 py-3 tabular-nums text-ink-secondary">
        {formatRowCount(job)}
      </td>
      <td className="whitespace-nowrap px-3 py-3 text-ink-tertiary">
        {formatDate(job.created_at)}
      </td>
      <td className="px-6 py-3 text-right">
        <div className="flex justify-end gap-2">
          {canDownload && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={onDownload}
            >
              {downloading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              下载
            </Button>
          )}
          {canRetry && (
            <Button type="button" variant="secondary" size="sm" disabled={busy} onClick={onRetry}>
              {retrying ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
              重试
            </Button>
          )}
          {!canDownload && !canRetry && (
            <span className="text-label-sm text-ink-tertiary">—</span>
          )}
        </div>
      </td>
    </>
  )
}
