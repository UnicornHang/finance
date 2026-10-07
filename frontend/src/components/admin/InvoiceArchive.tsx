import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, History, Receipt, Search, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader } from '@/components/ui/stat'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Table, TBody, TD, TH, THead, TR, EmptyState, Toolbar } from '@/components/ui/table'
import { exportApi } from '@/api/export'
import { invoiceApi } from '@/api/invoice'
import { readApiMessage } from '@/lib/apiError'
import type { Invoice } from '@/types'
import { formatCurrency, formatDate } from '@/lib/utils'

import { ExportCenter } from './ExportCenter'
import { InvoiceDetailDialog } from './InvoiceDetailDialog'
import { InvoiceListPager } from './InvoiceListPager'
import { STATUS_LABEL, STATUS_TONE, TYPE_LABEL, TYPE_TONE } from './invoiceMeta'

const DEFAULT_PAGE_SIZE = 10

/** 状态下拉。全部状态会合并待确认和已归档，已删除不进入列表。 */
const STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'pending_review', label: '待确认' },
  { value: 'active', label: '已归档' },
] as const

export function InvoiceArchive() {
  const queryClient = useQueryClient()
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('active')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [detail, setDetail] = useState<Invoice | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  /** 待确认删除的 id。单条来自详情，多条来自表格勾选。 */
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null)
  /** 导出中心抽屉开关与高亮任务 */
  const [exportCenterOpen, setExportCenterOpen] = useState(false)
  const [exportHighlightId, setExportHighlightId] = useState<string | null>(null)
  const appliedSearch = useRef(search)

  // 输入停顿后再查，避免每个字都打一页接口
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    if (appliedSearch.current === search) return
    appliedSearch.current = search
    setPage(1)
    setSelectedIds([])
  }, [search])

  const { data, isLoading } = useQuery({
    queryKey: ['invoices', page, pageSize, typeFilter, statusFilter, search],
    queryFn: () => {
      const invoiceType = typeFilter === 'all' ? undefined : typeFilter
      const query = {
        page,
        page_size: pageSize,
        invoice_type: invoiceType,
        search: search || undefined,
      }
      // 全部状态要合并三个真实状态，不能把 all 当作状态值去查
      if (statusFilter === 'all') return invoiceApi.listAllStatuses(query)
      return invoiceApi.list({ ...query, status_filter: statusFilter })
    },
    placeholderData: keepPreviousData,
  })

  const detailQuery = useQuery({
    queryKey: ['invoice', detail?.id],
    queryFn: () => invoiceApi.get(detail!.id),
    enabled: !!detail,
  })

  const fileQuery = useQuery({
    queryKey: ['invoice-file', detail?.id],
    queryFn: () => invoiceApi.downloadUrl(detail!.id),
    enabled: !!detail && detailQuery.isSuccess,
    retry: false,
  })

  const list = (data?.items ?? []).filter((inv) => inv.status !== 'deleted')
  const total = data?.total ?? 0

  const removeMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      const results = await Promise.allSettled(ids.map((id) => invoiceApi.remove(id)))
      const failed = results.filter((result) => result.status === 'rejected').length
      return { ok: ids.length - failed, failed }
    },
    onSuccess: (result, ids) => {
      if (result.failed === 0) {
        toast.success(ids.length === 1 ? '已删除' : `已删除 ${result.ok} 条`)
      } else if (result.ok === 0) {
        toast.error('删除失败')
      } else {
        toast.warning(`已删除 ${result.ok} 条，${result.failed} 条失败`)
      }
      setDetail((current) => (current && ids.includes(current.id) ? null : current))
      setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)))
      setPendingDelete(null)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      // 删除后记录离开列表；当前页被删空时退回上一页
      const targeted = list.filter((item) => ids.includes(item.id))
      const pageCleared =
        result.ok > 0 && targeted.length === list.length && result.ok >= targeted.length
      if (pageCleared && page > 1) setPage((current) => current - 1)
    },
  })

  /** 按当前筛选创建异步发票导出任务，并打开导出中心。 */
  const exportMutation = useMutation({
    mutationFn: () =>
      exportApi.create({
        resource_type: 'invoice',
        filters: {
          search,
          invoice_type: typeFilter === 'all' ? null : typeFilter,
          status_filter: statusFilter,
        },
      }),
    onSuccess: (job) => {
      if (job.deduplicated) {
        toast.info(job.message || '已有相同导出任务')
      } else {
        toast.success('已创建导出任务')
      }
      setExportHighlightId(job.id)
      setExportCenterOpen(true)
      void queryClient.invalidateQueries({ queryKey: ['exports'] })
    },
    onError: (err) => {
      toast.error(readApiMessage(err) || '创建导出失败')
    },
  })

  // 已删除记录再删会 404，当前页只允许勾选未删除的
  const selectableIds = list.filter((inv) => inv.status !== 'deleted').map((inv) => inv.id)
  const selectedOnPage = selectableIds.filter((id) => selectedIds.includes(id))
  const allChecked = selectableIds.length > 0 && selectedOnPage.length === selectableIds.length
  const someChecked = selectedOnPage.length > 0 && !allChecked

  /** 勾选或取消当前页可删的发票。 */
  function togglePage(checked: boolean) {
    setSelectedIds((prev) => {
      if (checked) return [...new Set([...prev, ...selectableIds])]
      const pageIds = new Set(selectableIds)
      return prev.filter((id) => !pageIds.has(id))
    })
  }

  /** 勾选或取消单行。 */
  function toggleOne(id: string, checked: boolean) {
    setSelectedIds((prev) => (checked ? [...prev, id] : prev.filter((item) => item !== id)))
  }

  function changePage(next: number) {
    setPage(next)
    setSelectedIds([])
  }

  // 筛选或删除后总页数变少，避免停在空白页
  useEffect(() => {
    if (!data) return
    const pages = Math.max(1, Math.ceil(total / pageSize))
    if (page > pages) {
      setPage(pages)
      setSelectedIds([])
    }
  }, [data, page, pageSize, total])

  /** 打开导出中心（不强制高亮）。 */
  function openExportCenter() {
    setExportHighlightId(null)
    setExportCenterOpen(true)
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        actions={
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" size="md" onClick={openExportCenter}>
              <History className="h-4 w-4" />
              导出记录
            </Button>
            <Button
              type="button"
              size="md"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              <Download className="h-4 w-4" />
              导出 Excel
            </Button>
          </div>
        }
      />

      <Card>
        <Toolbar>
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary" />
            <Input
              placeholder="搜索抬头 / 公司 / 发票号"
              className="h-9 pl-8"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <Select
            value={typeFilter}
            onValueChange={(v) => {
              setTypeFilter(v)
              setPage(1)
              setSelectedIds([])
            }}
          >
            <SelectTrigger className="h-9 w-32">
              <SelectValue placeholder="全部类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="special">专票</SelectItem>
              <SelectItem value="general">普票</SelectItem>
              <SelectItem value="electronic">电子发票</SelectItem>
              <SelectItem value="vehicle">机动车销售发票</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={statusFilter}
            onValueChange={(v) => {
              setStatusFilter(v)
              setPage(1)
              setSelectedIds([])
            }}
          >
            <SelectTrigger className="h-9 w-32">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="ml-auto flex items-center gap-2">
            {selectedIds.length > 0 && (
              <>
                <span className="text-body-sm tabular-nums text-ink-secondary">
                  已选 {selectedIds.length} 条
                </span>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setPendingDelete(selectedIds)}
                  disabled={removeMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                  删除
                </Button>
              </>
            )}
          </div>
        </Toolbar>

        <CardContent className="p-0">
          {isLoading ? (
            <EmptyState icon={<Receipt className="h-5 w-5" />} title="加载中..." />
          ) : list.length === 0 ? (
            <EmptyState
              icon={<Receipt className="h-5 w-5" />}
              title="暂无发票归档"
              description="上传的发票经 AI 识别后会自动归档到此处"
            />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH className="w-12">
                    <Checkbox
                      checked={allChecked ? true : someChecked ? 'indeterminate' : false}
                      disabled={selectableIds.length === 0}
                      onCheckedChange={(value) => togglePage(value === true)}
                      aria-label="全选当前页"
                    />
                  </TH>
                  <TH>发票抬头</TH>
                  <TH>开票公司</TH>
                  <TH>发票号码</TH>
                  <TH className="text-right">金额（含税）</TH>
                  <TH>类型</TH>
                  <TH>状态</TH>
                  <TH>开票日期</TH>
                  <TH>归档时间</TH>
                  <TH>操作用户</TH>
                </TR>
              </THead>
              <TBody>
                {list.map((inv) => (
                  <TR
                    key={inv.id}
                    className={
                      selectedIds.includes(inv.id) ? 'cursor-pointer bg-primary-tint' : 'cursor-pointer'
                    }
                    onClick={() => setDetail(inv)}
                  >
                    <TD onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.includes(inv.id)}
                        disabled={inv.status === 'deleted'}
                        onCheckedChange={(value) => toggleOne(inv.id, value === true)}
                        aria-label={`选择 ${inv.invoice_title || inv.invoice_number || '发票'}`}
                      />
                    </TD>
                    <TD className="font-semibold">{inv.invoice_title || '-'}</TD>
                    <TD className="text-ink-secondary">{inv.company || '-'}</TD>
                    <TD className="font-mono text-body-sm">
                      {inv.invoice_number || '-'}
                    </TD>
                    <TD className="text-right tabular-nums font-semibold">
                      {formatCurrency(inv.amount_incl_tax)}
                    </TD>
                    <TD>
                      {inv.invoice_type && (
                        <Badge tone={TYPE_TONE[inv.invoice_type] || 'neutral'}>
                          {TYPE_LABEL[inv.invoice_type] || inv.invoice_type}
                        </Badge>
                      )}
                    </TD>
                    <TD>
                      <Badge tone={STATUS_TONE[inv.status] || 'neutral'}>
                        {STATUS_LABEL[inv.status] || inv.status}
                      </Badge>
                    </TD>
                    <TD className="text-ink-tertiary tabular-nums">
                      {inv.invoice_date || '-'}
                    </TD>
                    <TD className="text-ink-tertiary">{formatDate(inv.created_at)}</TD>
                    <TD className="text-ink-secondary">{inv.operator_name || '-'}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
          {!(isLoading && !data) && (
            <InvoiceListPager
              page={page}
              pageSize={pageSize}
              total={total}
              onPageChange={changePage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
                setSelectedIds([])
              }}
            />
          )}
        </CardContent>
      </Card>

      <InvoiceDetailDialog
        preview={detail}
        invoice={detailQuery.data}
        loading={detailQuery.isLoading}
        fileUrl={fileQuery.data?.url}
        fileLoading={fileQuery.isFetching}
        deleting={removeMutation.isPending}
        onClose={() => setDetail(null)}
        onRequestFile={() => {
          void fileQuery.refetch()
        }}
        onRequestDelete={() => {
          if (!detail) return
          setPendingDelete([detail.id])
        }}
      />

      <AlertDialog
        open={!!pendingDelete}
        onOpenChange={(open) => {
          if (!open && !removeMutation.isPending) setPendingDelete(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {(pendingDelete?.length ?? 0) > 1
                ? `确定删除选中的 ${pendingDelete?.length} 张发票？`
                : '确定删除该发票？'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              删除后这些发票将从档案列表中移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removeMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!pendingDelete?.length) return
                removeMutation.mutate(pendingDelete)
              }}
              disabled={removeMutation.isPending}
            >
              {removeMutation.isPending ? '删除中...' : '确定'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ExportCenter
        open={exportCenterOpen}
        onOpenChange={setExportCenterOpen}
        highlightId={exportHighlightId}
        defaultResourceType="invoice"
      />
    </div>
  )
}
