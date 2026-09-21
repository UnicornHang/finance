import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Download,
  ExternalLink,
  FileText,
  Filter,
  Loader2,
  Receipt,
  Search,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent } from '@/components/ui/card'
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { Field } from '@/components/ui/surface'
import { Table, TBody, TD, TH, THead, TR, EmptyState, Toolbar } from '@/components/ui/table'
import { invoiceApi } from '@/api/invoice'
import type { Invoice } from '@/types'
import { formatCurrency, formatDate } from '@/lib/utils'

const TYPE_LABEL: Record<string, string> = {
  special: '专票',
  general: '普票',
  electronic: '电子发票',
}

const TYPE_TONE: Record<string, 'primary' | 'success' | 'neutral'> = {
  special: 'primary',
  general: 'success',
  electronic: 'neutral',
}

const STATUS_LABEL: Record<string, string> = {
  pending_review: '待确认',
  active: '已归档',
  deleted: '已删除',
}

const STATUS_TONE: Record<string, 'primary' | 'success' | 'neutral' | 'warning'> = {
  pending_review: 'warning',
  active: 'success',
  deleted: 'neutral',
}

const CSV_COLUMNS: Array<{ key: keyof Invoice; label: string }> = [
  { key: 'invoice_title', label: '发票抬头' },
  { key: 'company', label: '开票公司' },
  { key: 'tax_id', label: '纳税人识别号' },
  { key: 'invoice_code', label: '发票代码' },
  { key: 'invoice_number', label: '发票号码' },
  { key: 'invoice_date', label: '开票日期' },
  { key: 'amount_excl_tax', label: '不含税金额' },
  { key: 'tax_amount', label: '税额' },
  { key: 'amount_incl_tax', label: '含税合计' },
  { key: 'invoice_type', label: '发票类型' },
  { key: 'seller', label: '销售方' },
  { key: 'buyer', label: '购买方' },
  { key: 'remark', label: '备注' },
  { key: 'status', label: '状态' },
  { key: 'created_at', label: '归档时间' },
]

function escapeCsvCell(v: unknown): string {
  if (v === null || v === undefined) return ''
  const s = String(v)
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function buildCsv(rows: Invoice[]): string {
  const header = CSV_COLUMNS.map((c) => escapeCsvCell(c.label)).join(',')
  const body = rows
    .map((r) =>
      CSV_COLUMNS.map((c) => {
        const v = r[c.key]
        if (c.key === 'invoice_type') return escapeCsvCell(TYPE_LABEL[String(v)] || v)
        if (c.key === 'status') return escapeCsvCell(STATUS_LABEL[String(v)] || v)
        return escapeCsvCell(v)
      }).join(','),
    )
    .join('\n')
  // 加 BOM 让 Excel 正确识别 UTF-8
  return '﻿' + header + '\n' + body
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function InvoiceArchive() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [detail, setDetail] = useState<Invoice | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['invoices', page, pageSize, typeFilter, statusFilter],
    queryFn: () =>
      invoiceApi.list({
        page,
        page_size: pageSize,
        invoice_type: typeFilter || undefined,
        status_filter: statusFilter || undefined,
      }),
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

  const removeMutation = useMutation({
    mutationFn: (id: string) => invoiceApi.remove(id),
    onSuccess: () => {
      toast.success('已删除')
      setDetail(null)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || '删除失败')
    },
  })

  const allItems = data?.items ?? []
  const total = data?.total ?? 0

  const list = useMemo(() => {
    if (!search.trim()) return allItems
    const q = search.toLowerCase()
    return allItems.filter((inv) =>
      `${inv.invoice_title ?? ''} ${inv.company ?? ''} ${inv.invoice_number ?? ''}`
        .toLowerCase()
        .includes(q),
    )
  }, [allItems, search])

  const handleExportCsv = () => {
    if (list.length === 0) {
      toast.warning('当前列表为空，无可导出数据')
      return
    }
    const csv = buildCsv(list)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    downloadBlob(blob, `invoices-${ts}.csv`)
    toast.success(`已导出 ${list.length} 条记录`)
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="档案"
        description="检索、筛选与导出发票原始凭证与结构化字段"
        actions={
          <>
            <Button variant="secondary" size="md">
              <Filter className="h-4 w-4" />
              高级筛选
            </Button>
            <Button size="md" onClick={handleExportCsv}>
              <Download className="h-4 w-4" />
              导出 CSV
            </Button>
          </>
        }
      />

      <Card>
        <Toolbar>
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary" />
            <Input
              placeholder="搜索抬头 / 公司 / 发票号"
              className="h-9 pl-8"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select
            value={typeFilter}
            onValueChange={(v) => {
              setTypeFilter(v)
              setPage(1)
            }}
          >
            <SelectTrigger className="h-9 w-32">
              <SelectValue placeholder="全部类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">全部类型</SelectItem>
              <SelectItem value="special">专票</SelectItem>
              <SelectItem value="general">普票</SelectItem>
              <SelectItem value="electronic">电子发票</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={statusFilter}
            onValueChange={(v) => {
              setStatusFilter(v)
              setPage(1)
            }}
          >
            <SelectTrigger className="h-9 w-32">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="active">已归档</SelectItem>
              <SelectItem value="pending_review">待确认</SelectItem>
              <SelectItem value="">全部状态</SelectItem>
            </SelectContent>
          </Select>
          <span className="ml-auto text-body-sm text-ink-tertiary tabular-nums">
            共 {total} 条
          </span>
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
                  <TH>发票抬头</TH>
                  <TH>开票公司</TH>
                  <TH>发票号码</TH>
                  <TH className="text-right">金额（含税）</TH>
                  <TH>类型</TH>
                  <TH>状态</TH>
                  <TH>开票日期</TH>
                  <TH>归档时间</TH>
                  <TH className="w-16">操作</TH>
                </TR>
              </THead>
              <TBody>
                {list.map((inv) => (
                  <TR
                    key={inv.id}
                    className="cursor-pointer"
                    onClick={() => setDetail(inv)}
                  >
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
                    <TD onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDetail(inv)}
                      >
                        详情
                      </Button>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {total > pageSize && (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </Button>
          <span className="text-body-sm tabular-nums text-ink-tertiary">
            第 {page} / {Math.ceil(total / pageSize)} 页
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page * pageSize >= total}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </Button>
        </div>
      )}

      {/* 详情对话框 */}
      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>发票详情</DialogTitle>
            <DialogDescription>
              {detailQuery.data?.invoice_title ||
                detail?.invoice_title ||
                '查看发票完整字段'}
            </DialogDescription>
          </DialogHeader>

          {detailQuery.isLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-ink-tertiary" />
            </div>
          ) : detailQuery.data ? (
            <div className="space-y-5 pt-2">
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-body-sm">
                <Field label="发票抬头">
                  <div>{detailQuery.data.invoice_title || '-'}</div>
                </Field>
                <Field label="开票公司">
                  <div>{detailQuery.data.company || '-'}</div>
                </Field>
                <Field label="纳税人识别号">
                  <div className="font-mono">{detailQuery.data.tax_id || '-'}</div>
                </Field>
                <Field label="发票类型">
                  <div>
                    {detailQuery.data.invoice_type ? (
                      <Badge tone={TYPE_TONE[detailQuery.data.invoice_type] || 'neutral'}>
                        {TYPE_LABEL[detailQuery.data.invoice_type] ||
                          detailQuery.data.invoice_type}
                      </Badge>
                    ) : (
                      '-'
                    )}
                  </div>
                </Field>
                <Field label="发票代码">
                  <div className="font-mono">{detailQuery.data.invoice_code || '-'}</div>
                </Field>
                <Field label="发票号码">
                  <div className="font-mono">
                    {detailQuery.data.invoice_number || '-'}
                  </div>
                </Field>
                <Field label="开票日期">
                  <div className="tabular-nums">
                    {detailQuery.data.invoice_date || '-'}
                  </div>
                </Field>
                <Field label="状态">
                  <Badge tone={STATUS_TONE[detailQuery.data.status] || 'neutral'}>
                    {STATUS_LABEL[detailQuery.data.status] || detailQuery.data.status}
                  </Badge>
                </Field>
                <Field label="销售方">
                  <div>{detailQuery.data.seller || '-'}</div>
                </Field>
                <Field label="购买方">
                  <div>{detailQuery.data.buyer || '-'}</div>
                </Field>
                <Field label="不含税金额">
                  <div className="tabular-nums">
                    {formatCurrency(detailQuery.data.amount_excl_tax)}
                  </div>
                </Field>
                <Field label="税额">
                  <div className="tabular-nums">
                    {formatCurrency(detailQuery.data.tax_amount)}
                  </div>
                </Field>
                <Field label="含税合计">
                  <div className="tabular-nums font-semibold">
                    {formatCurrency(detailQuery.data.amount_incl_tax)}
                  </div>
                </Field>
                <Field label="归档时间">
                  <div className="text-ink-tertiary">
                    {formatDate(detailQuery.data.created_at)}
                  </div>
                </Field>
              </div>

              {detailQuery.data.remark && (
                <Field label="备注">
                  <div className="rounded border border-line-subtle bg-canvas px-3 py-2 text-body-sm">
                    {detailQuery.data.remark}
                  </div>
                </Field>
              )}

              {detailQuery.data.file_hash && (
                <div className="rounded-md border border-line-subtle bg-canvas px-3 py-2 text-body-sm text-ink-tertiary">
                  文件指纹：<span className="font-mono text-ink">
                    {detailQuery.data.file_hash.slice(0, 16)}…
                  </span>
                </div>
              )}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => fileQuery.refetch()}
              disabled={fileQuery.isFetching || !detailQuery.data}
            >
              {fileQuery.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              获取下载链接
            </Button>
            {fileQuery.data?.url && (
              <Button asChild variant="primary">
                <a
                  href={fileQuery.data.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink className="h-4 w-4" />
                  下载原件
                </a>
              </Button>
            )}
            <Button
              variant="danger"
              onClick={() => setConfirmDelete(true)}
              disabled={removeMutation.isPending || !detailQuery.data}
            >
              <Trash2 className="h-4 w-4" />
              删除
            </Button>
            <Button variant="secondary" onClick={() => setDetail(null)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 AlertDialog —— 替代原生 confirm() */}
      <AlertDialog
        open={confirmDelete}
        onOpenChange={(o) => {
          if (!o && !removeMutation.isPending) setConfirmDelete(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确定删除该发票？</AlertDialogTitle>
            <AlertDialogDescription>
              此操作不可撤销，发票记录将从档案中移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removeMutation.isPending}>
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!detail) return
                removeMutation.mutate(detail.id)
                setConfirmDelete(false)
              }}
              disabled={removeMutation.isPending}
            >
              {removeMutation.isPending ? '删除中...' : '确定'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 隐藏的文件图标，避免未使用警告 */}
      <span className="hidden">
        <FileText className="h-4 w-4" />
      </span>
    </div>
  )
}
