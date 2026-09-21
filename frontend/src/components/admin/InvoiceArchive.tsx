import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Filter, Receipt, Search } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader } from '@/components/ui/stat'
import { Table, TBody, TD, TH, THead, TR, EmptyState, Toolbar } from '@/components/ui/table'
import { invoiceApi } from '@/api/invoice'
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

export function InvoiceArchive() {
  const { data: invoices, isLoading } = useQuery({
    queryKey: ['invoices'],
    queryFn: () => invoiceApi.list(),
  })

  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const list = (invoices || []).filter((inv) => {
    if (typeFilter && inv.invoice_type !== typeFilter) return false
    if (
      search &&
      !(`${inv.invoice_title} ${inv.company} ${inv.invoice_number}`
        .toLowerCase()
        .includes(search.toLowerCase()))
    )
      return false
    return true
  })

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
            <Button size="md">
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
            className="h-9 w-40"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">全部类型</option>
            <option value="special">专票</option>
            <option value="general">普票</option>
            <option value="electronic">电子发票</option>
          </Select>
          <span className="ml-auto text-body-sm text-ink-tertiary tabular-nums">
            共 {list.length} 条
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
                  <TH>开票日期</TH>
                  <TH>归档时间</TH>
                </TR>
              </THead>
              <TBody>
                {list.map((inv) => (
                  <TR key={inv.id}>
                    <TD className="font-semibold">{inv.invoice_title || '-'}</TD>
                    <TD className="text-ink-secondary">{inv.company || '-'}</TD>
                    <TD className="font-mono text-body-sm">{inv.invoice_number || '-'}</TD>
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
                    <TD className="text-ink-tertiary tabular-nums">
                      {inv.invoice_date || '-'}
                    </TD>
                    <TD className="text-ink-tertiary">{formatDate(inv.created_at)}</TD>
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