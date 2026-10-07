import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileText, History, Search, Trash2 } from 'lucide-react'
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
import { RiskBadge } from '@/components/sidepanel/RiskBadge'
import { contractApi } from '@/api/contract'
import { exportApi } from '@/api/export'
import { fileApi } from '@/api/file'
import { usePresignedFileActions } from '@/hooks/usePresignedFileActions'
import { readApiMessage } from '@/lib/apiError'
import type { Contract } from '@/types'
import { formatCurrency, formatDate } from '@/lib/utils'

import { ContractDetailDialog } from './ContractDetailDialog'
import { ExportCenter } from './ExportCenter'
import { InvoiceListPager } from './InvoiceListPager'

const DEFAULT_PAGE_SIZE = 10

export function ContractArchive() {
  const queryClient = useQueryClient()
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [detail, setDetail] = useState<Contract | null>(null)
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
    queryKey: ['contracts', page, pageSize, riskFilter, search],
    queryFn: () =>
      contractApi.list({
        page,
        page_size: pageSize,
        search: search || undefined,
        risk_level: riskFilter || undefined,
      }),
    placeholderData: keepPreviousData,
  })

  const detailQuery = useQuery({
    queryKey: ['contract', detail?.id],
    queryFn: () => contractApi.get(detail!.id),
    enabled: !!detail,
  })

  // 合同原件走通用预签名，按需换取，无独立 /contracts/{id}/file
  const fileQuery = useQuery({
    queryKey: ['contract-file', detail?.id, detailQuery.data?.file_url],
    queryFn: () => fileApi.presign(detailQuery.data!.file_url!),
    enabled: false,
    retry: false,
  })
  const { copyDownloadLink, downloadOriginal, fileLoading } = usePresignedFileActions({
    refetch: fileQuery.refetch,
    cachedUrl: fileQuery.data?.url,
    isFetching: fileQuery.isFetching,
    fetchDownloadUrl: async () => {
      const fileUrl = detailQuery.data?.file_url
      if (!fileUrl) throw new Error('缺少合同原件地址')
      const result = await fileApi.presign(fileUrl, 3600, true)
      if (!result.url) throw new Error('获取下载链接失败')
      return result.url
    },
  })

  const list = data?.items ?? []
  const total = data?.total ?? 0
  const stats = data?.risk_counts ?? { high: 0, medium: 0, low: 0 }

  const removeMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      const results = await Promise.allSettled(ids.map((id) => contractApi.remove(id)))
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
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
      // 当前页被删空时退回上一页
      const targeted = list.filter((item) => ids.includes(item.id))
      const pageCleared =
        result.ok > 0 && targeted.length === list.length && result.ok >= targeted.length
      if (pageCleared && page > 1) setPage((current) => current - 1)
    },
  })

  /** 按当前 search/risk 创建异步合同导出任务（后端查库，不依赖当前页）。 */
  const exportMutation = useMutation({
    mutationFn: () =>
      exportApi.create({
        resource_type: 'contract',
        filters: {
          search,
          risk_level: riskFilter || null,
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

  /** 打开导出中心（不强制高亮）。 */
  function openExportCenter() {
    setExportHighlightId(null)
    setExportCenterOpen(true)
  }

  const selectableIds = list.map((c) => c.id)
  const selectedOnPage = selectableIds.filter((id) => selectedIds.includes(id))
  const allChecked = selectableIds.length > 0 && selectedOnPage.length === selectableIds.length
  const someChecked = selectedOnPage.length > 0 && !allChecked

  /** 勾选或取消当前页全部合同。 */
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
              导出报告
            </Button>
          </div>
        }
      />

      {/* Risk overview strip */}
      <div className="grid gap-4 sm:grid-cols-3">
        <RiskStatCard label="高风险" value={stats.high || 0} tone="danger" />
        <RiskStatCard label="中风险" value={stats.medium || 0} tone="warning" />
        <RiskStatCard label="低风险" value={stats.low || 0} tone="success" />
      </div>

      <Card>
        <Toolbar>
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary" />
            <Input
              placeholder="搜索合同 / 甲方 / 乙方"
              className="h-9 pl-8"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <Select
            value={riskFilter}
            onValueChange={(v) => {
              setRiskFilter(v)
              setPage(1)
              setSelectedIds([])
            }}
          >
            <SelectTrigger className="h-9 w-40">
              <SelectValue placeholder="全部风险" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">全部风险</SelectItem>
              <SelectItem value="high">高风险</SelectItem>
              <SelectItem value="medium">中风险</SelectItem>
              <SelectItem value="low">低风险</SelectItem>
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
            <EmptyState icon={<FileText className="h-5 w-5" />} title="加载中..." />
          ) : list.length === 0 ? (
            <EmptyState
              icon={<FileText className="h-5 w-5" />}
              title="暂无合同"
              description="上传的合同经 AI 审查后会归档到此处"
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
                  <TH>合同名称</TH>
                  <TH>甲方</TH>
                  <TH>乙方</TH>
                  <TH className="text-right">金额</TH>
                  <TH>风险等级</TH>
                  <TH>签订日期</TH>
                </TR>
              </THead>
              <TBody>
                {list.map((c) => (
                  <TR
                    key={c.id}
                    className={
                      selectedIds.includes(c.id) ? 'cursor-pointer bg-primary-tint' : 'cursor-pointer'
                    }
                    onClick={() => setDetail(c)}
                  >
                    <TD onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.includes(c.id)}
                        onCheckedChange={(value) => toggleOne(c.id, value === true)}
                        aria-label={`选择 ${c.contract_name || '合同'}`}
                      />
                    </TD>
                    <TD className="font-semibold text-primary hover:underline">
                      {c.contract_name || '-'}
                    </TD>
                    <TD className="text-ink-secondary">{c.party_a || '-'}</TD>
                    <TD className="text-ink-secondary">{c.party_b || '-'}</TD>
                    <TD className="text-right tabular-nums font-semibold">
                      {formatCurrency(c.amount)}
                    </TD>
                    <TD>
                      <RiskBadge level={c.risk_level} />
                    </TD>
                    <TD className="text-ink-tertiary">
                      {formatDate(c.sign_date) || c.sign_date || '-'}
                    </TD>
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

      <ContractDetailDialog
        preview={detail}
        contract={detailQuery.data}
        loading={detailQuery.isLoading}
        fileLoading={fileLoading}
        deleting={removeMutation.isPending}
        onClose={() => setDetail(null)}
        onCopyDownloadLink={() => {
          void copyDownloadLink()
        }}
        onDownloadOriginal={() => {
          void downloadOriginal()
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
                ? `确定删除选中的 ${pendingDelete?.length} 份合同？`
                : '确定删除该合同？'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              删除后这些合同将从档案列表中移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removeMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={removeMutation.isPending}
              onClick={() => {
                if (!pendingDelete?.length) return
                removeMutation.mutate(pendingDelete)
              }}
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
        defaultResourceType="contract"
      />
    </div>
  )
}

function RiskStatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'danger' | 'warning' | 'success'
}) {
  const colorMap = {
    danger: 'border-danger-border bg-danger-tint text-danger',
    warning: 'border-warning-border bg-warning-tint text-warning',
    success: 'border-success-border bg-success-tint text-success',
  }
  return (
    <div className={`rounded-lg border px-5 py-4 ${colorMap[tone]}`}>
      <p className="text-label-md font-semibold uppercase tracking-wider opacity-80">
        {label}
      </p>
      <p className="mt-1 text-numeric-lg font-semibold tabular-nums">{value}</p>
      <p className="text-label-sm opacity-70">份合同</p>
    </div>
  )
}
