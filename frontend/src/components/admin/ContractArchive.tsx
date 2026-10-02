import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileText, Search } from 'lucide-react'
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
import { fileApi } from '@/api/file'
import type { Contract } from '@/types'
import { formatCurrency, formatDate } from '@/lib/utils'

import { ContractDetailDialog } from './ContractDetailDialog'

export function ContractArchive() {
  const queryClient = useQueryClient()
  const { data: contracts, isLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractApi.list(),
  })

  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [detail, setDetail] = useState<Contract | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const detailQuery = useQuery({
    queryKey: ['contract', detail?.id],
    queryFn: () => contractApi.get(detail!.id),
    enabled: !!detail,
  })

  // 合同原件走通用预签名，无独立 /contracts/{id}/file
  const fileQuery = useQuery({
    queryKey: ['contract-file', detail?.id, detailQuery.data?.file_url],
    queryFn: () => fileApi.presign(detailQuery.data!.file_url!),
    enabled: !!detail && !!detailQuery.data?.file_url,
    retry: false,
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => contractApi.remove(id),
    onSuccess: () => {
      toast.success('已删除')
      setDetail(null)
      setPendingDelete(null)
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
    },
    onError: () => {
      toast.error('删除失败')
    },
  })

  const list = (contracts || []).filter((c) => {
    if (riskFilter && c.risk_level !== riskFilter) return false
    if (
      search &&
      !`${c.contract_name} ${c.party_a} ${c.party_b}`.toLowerCase().includes(search.toLowerCase())
    )
      return false
    return true
  })

  // Risk summary
  const stats = (contracts || []).reduce(
    (acc, c) => {
      const level = c.risk_level || 'low'
      acc[level] = (acc[level] || 0) + 1
      return acc
    },
    {} as Record<string, number>,
  )

  return (
    <div className="space-y-6">
      <SectionHeader
        actions={
          <Button size="md">
            <Download className="h-4 w-4" />
            导出报告
          </Button>
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
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select value={riskFilter} onValueChange={setRiskFilter}>
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
          <span className="ml-auto text-body-sm text-ink-tertiary tabular-nums">
            共 {list.length} 份
          </span>
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
                    className="cursor-pointer"
                    onClick={() => setDetail(c)}
                  >
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
        </CardContent>
      </Card>

      <ContractDetailDialog
        preview={detail}
        contract={detailQuery.data}
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
          setPendingDelete(detail.id)
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
            <AlertDialogTitle>确定删除该合同？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后该合同将从档案列表中移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removeMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={removeMutation.isPending}
              onClick={() => {
                if (!pendingDelete) return
                removeMutation.mutate(pendingDelete)
              }}
            >
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
