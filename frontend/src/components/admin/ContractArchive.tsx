import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, FileText, Search } from 'lucide-react'

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
import { Table, TBody, TD, TH, THead, TR, EmptyState, Toolbar } from '@/components/ui/table'
import { RiskBadge } from '@/components/sidepanel/RiskBadge'
import { contractApi } from '@/api/contract'
import { formatCurrency, formatDate } from '@/lib/utils'

export function ContractArchive() {
  const { data: contracts, isLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractApi.list(),
  })

  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('')

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
        title="合规"
        description="所有合同的合规审查结果与归档凭证"
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
                  <TR key={c.id}>
                    <TD className="font-semibold">{c.contract_name || '-'}</TD>
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