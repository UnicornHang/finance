import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  CircleDollarSign,
  FileText,
  Receipt,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { cn, formatCurrency, formatDate } from '@/lib/utils'
import { StatCard } from '@/components/ui/stat'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RiskBadge } from '@/components/sidepanel/RiskBadge'
import { dashboardApi } from '@/api/admin'
import type { DashboardKpi, DashboardOverview, DashboardTrendPoint } from '@/types'

type TrendRange = 7 | 30

/** 将接口风险字段收敛为徽章可用的三档。 */
function toRiskLevel(level: string): 'high' | 'medium' | 'low' {
  switch (level) {
    case 'high':
      return 'high'
    case 'medium':
      return 'medium'
    case 'low':
      return 'low'
    default:
      return 'medium'
  }
}

/** 环比方向：增长为成功，下降为警示。 */
function kpiTone(delta: number | null): 'success' | 'danger' | 'neutral' {
  if (delta === null || delta === 0) return 'neutral'
  return delta > 0 ? 'success' : 'danger'
}

/** 金额 KPI 展示，整数部分用千分位。 */
function formatKpiAmount(value: number): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  }).format(value)
}

/**
 * 首页数据概览：接 /dashboard/overview，展示 KPI、趋势、风险与最近归档。
 */
export function Dashboard() {
  const [days, setDays] = useState<TrendRange>(7)
  const query = useQuery({
    queryKey: ['dashboard', 'overview', days],
    queryFn: () => dashboardApi.overview(days),
  })

  if (query.isLoading) {
    return <DashboardSkeleton />
  }

  if (query.isError || !query.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>数据概览暂时无法加载</CardTitle>
          <CardDescription>请稍后重试，或检查网络与登录状态。</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="secondary" onClick={() => query.refetch()}>
            重新加载
          </Button>
        </CardContent>
      </Card>
    )
  }

  return <DashboardBody data={query.data} days={days} onDaysChange={setDays} />
}

function DashboardBody({
  data,
  days,
  onDaysChange,
}: {
  data: DashboardOverview
  days: TrendRange
  onDaysChange: (days: TrendRange) => void
}) {
  const { kpis } = data
  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="今日归档"
          value={kpis.today_archived.value.toLocaleString('zh-CN')}
          suffix="笔"
          kpi={kpis.today_archived}
          deltaLabel="较昨日"
          icon={<Receipt className="h-3.5 w-3.5" />}
        />
        <KpiCard
          label="本月发票总额"
          value={formatKpiAmount(kpis.month_invoice_amount.value)}
          kpi={kpis.month_invoice_amount}
          deltaLabel="本月确认归档 · 较上月"
          icon={<CircleDollarSign className="h-3.5 w-3.5" />}
        />
        <KpiCard
          label="本月归档合同"
          value={kpis.month_contracts.value.toLocaleString('zh-CN')}
          suffix="份"
          kpi={kpis.month_contracts}
          deltaLabel="本月确认归档 · 较上月"
          icon={<FileText className="h-3.5 w-3.5" />}
        />
        <StatCard
          label="高风险合同"
          value={kpis.high_risk_contracts.value.toLocaleString('zh-CN')}
          suffix="份"
          tone={kpis.high_risk_contracts.value > 0 ? 'danger' : 'success'}
          deltaLabel={kpis.high_risk_contracts.value > 0 ? '需关注' : '暂无'}
          icon={<ShieldAlert className="h-3.5 w-3.5" />}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>近 {days} 天归档趋势</CardTitle>
                <CardDescription>已确认归档的发票与合同</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <RangeToggle days={days} onChange={onDaysChange} />
                <TrendBadge delta={data.trend.delta_pct} />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <TrendChart points={data.trend.points} />
            <div className="mt-4 flex items-center justify-between text-body-sm text-ink-tertiary">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-primary" />
                  发票
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-success" />
                  合同
                </span>
              </div>
              <span>更新时间 {formatDate(data.generated_at)}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>风险合同</CardTitle>
            <CardDescription>高/中风险已归档合同</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.risk_contracts.length === 0 ? (
              <p className="text-body-md text-ink-tertiary">当前没有高/中风险合同</p>
            ) : (
              data.risk_contracts.map((item) => (
                <RiskItem
                  key={item.id}
                  id={item.id}
                  title={item.title}
                  amount={item.amount}
                  level={toRiskLevel(item.risk_level)}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>本月活跃</CardTitle>
            <CardDescription>登录会话 / 上传 / 问答</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              <ActivityItem label="活跃用户" value={data.activity.active_users.toLocaleString('zh-CN')} suffix="人" />
              <ActivityItem label="上传发票" value={data.activity.invoices_uploaded.toLocaleString('zh-CN')} suffix="张" />
              <ActivityItem label="制度问答" value={data.activity.policy_queries.toLocaleString('zh-CN')} suffix="次" />
              <ActivityItem label="合同审查" value={data.activity.contract_reviews.toLocaleString('zh-CN')} suffix="份" />
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>财务摘要</CardTitle>
            <CardDescription>本月确认归档的发票</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <SummaryRow label="不含税总额" value={formatCurrency(data.finance.amount_excl_tax)} />
            <SummaryRow label="税额合计" value={formatCurrency(data.finance.tax_amount)} />
            <SummaryRow label="专票进项税额" value={formatCurrency(data.finance.input_tax)} />
            <div className="my-2 h-px bg-line-subtle" />
            <SummaryRow label="含税合计" value={formatCurrency(data.finance.amount_incl_tax)} bold />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>知识库</CardTitle>
            <CardDescription>制度文档索引；检索含对话问答与后台测试</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Stat label="文档总数" value={data.knowledge.document_count.toLocaleString('zh-CN')} />
            <Stat label="向量块数" value={data.knowledge.chunk_count.toLocaleString('zh-CN')} />
            <Stat label="本月检索" value={data.knowledge.month_retrieves.toLocaleString('zh-CN')} />
            <KnowledgeStatus knowledge={data.knowledge} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>最近归档</CardTitle>
          <CardDescription>确认入库的发票与合同</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.recent_archives.length === 0 ? (
            <p className="text-body-md text-ink-tertiary">暂无归档记录</p>
          ) : (
            data.recent_archives.map((item) => (
              <RecentRow key={`${item.kind}-${item.id}-${item.created_at}`} item={item} />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function KpiCard({
  label,
  value,
  suffix,
  kpi,
  deltaLabel,
  icon,
}: {
  label: string
  value: string
  suffix?: string
  kpi: DashboardKpi
  deltaLabel: string
  icon: ReactNode
}) {
  return (
    <StatCard
      label={label}
      value={value}
      suffix={suffix}
      delta={kpi.delta_pct ?? undefined}
      tone={kpiTone(kpi.delta_pct)}
      deltaLabel={deltaLabel}
      icon={icon}
    />
  )
}

function RangeToggle({ days, onChange }: { days: TrendRange; onChange: (days: TrendRange) => void }) {
  return (
    <div className="flex rounded-md border border-line p-0.5">
      {([7, 30] as const).map((value) => (
        <Button
          key={value}
          type="button"
          size="sm"
          variant={days === value ? 'primary' : 'ghost'}
          onClick={() => onChange(value)}
        >
          {value} 天
        </Button>
      ))}
    </div>
  )
}

function TrendBadge({ delta }: { delta: number | null }) {
  if (delta === null) {
    return (
      <Badge tone="neutral" dot>
        暂无环比
      </Badge>
    )
  }
  const up = delta >= 0
  return (
    <Badge tone={up ? 'primary' : 'warning'} dot>
      {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
      {up ? '上升' : '下降'} {Math.abs(delta).toFixed(1)}%
    </Badge>
  )
}

function RiskItem({
  id,
  title,
  amount,
  level,
}: {
  id: string
  title: string
  amount: number
  level: 'high' | 'medium' | 'low'
}) {
  return (
    <Link
      to="/admin/contracts"
      className="flex items-center justify-between rounded-md border border-line bg-canvas px-3 py-2.5 hover:border-line-strong"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-body-md font-semibold text-ink">{title}</p>
        <p className="text-label-sm text-ink-tertiary tabular-nums">{formatCurrency(amount)}</p>
      </div>
      <RiskBadge level={level} />
      <span className="sr-only">{id}</span>
    </Link>
  )
}

function ActivityItem({ label, value, suffix }: { label: string; value: string; suffix?: string }) {
  return (
    <li className="flex items-center justify-between">
      <span className="text-body-md text-ink-secondary">{label}</span>
      <span className="text-numeric-md font-semibold text-ink tabular-nums">
        {value}
        {suffix && <span className="ml-1 text-body-sm text-ink-tertiary">{suffix}</span>}
      </span>
    </li>
  )
}

function SummaryRow({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="flex items-center justify-between text-body-md">
      <span className="text-ink-secondary">{label}</span>
      <span className={cn('tabular-nums', bold ? 'text-numeric-md font-semibold text-ink' : 'text-ink')}>
        {value}
      </span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-body-md">
      <span className="text-ink-secondary">{label}</span>
      <span className="font-semibold tabular-nums text-ink">{value}</span>
    </div>
  )
}

function KnowledgeStatus({
  knowledge,
}: {
  knowledge: DashboardOverview['knowledge']
}) {
  if (knowledge.document_count === 0) {
    return (
      <div className="rounded-md border border-line bg-canvas px-3 py-2 text-body-sm text-ink-tertiary">
        暂无知识库文档
      </div>
    )
  }
  if (knowledge.all_indexed) {
    return (
      <div className="rounded-md border border-success-border bg-success-tint px-3 py-2 text-body-sm text-success">
        所有文档均已索引完成
      </div>
    )
  }
  return (
    <div className="rounded-md border border-warning-border bg-warning-tint px-3 py-2 text-body-sm text-warning">
      {knowledge.pending_or_failed} 份文档未完成索引
    </div>
  )
}

function RecentRow({ item }: { item: DashboardOverview['recent_archives'][number] }) {
  const to = item.kind === 'contract' ? '/admin/contracts' : '/admin/invoices'
  return (
    <Link
      to={to}
      className="flex items-center justify-between gap-3 rounded-md border border-line bg-canvas px-3 py-2.5 hover:border-line-strong"
    >
      <div className="min-w-0">
        <p className="truncate text-body-md font-semibold text-ink">{item.title}</p>
        <p className="text-label-sm text-ink-tertiary">
          {item.kind === 'contract' ? '合同' : '发票'}
          {item.operator_name ? ` · ${item.operator_name}` : ''}
          {item.created_at ? ` · ${formatDate(item.created_at)}` : ''}
        </p>
      </div>
      <span className="shrink-0 text-body-md tabular-nums text-ink">
        {item.amount === null || item.amount === undefined ? '-' : formatCurrency(item.amount)}
      </span>
    </Link>
  )
}

/** Recharts 堆叠柱：发票 / 合同归档量。 */
function TrendChart({ points }: { points: DashboardTrendPoint[] }) {
  const dense = points.length > 10
  return (
    <div className="h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={dense ? '20%' : '28%'}>
          <CartesianGrid stroke="#e6e9f0" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey={dense ? 'label' : 'weekday'}
            axisLine={false}
            tickLine={false}
            interval={dense ? 2 : 0}
            tick={{ fontSize: 12, fill: '#6b7691' }}
          />
          <YAxis
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            width={28}
            tick={{ fontSize: 12, fill: '#6b7691' }}
          />
          <Tooltip
            cursor={{ fill: '#f3f5f9' }}
            content={<TrendTooltip />}
          />
          <Bar dataKey="invoices" name="发票" stackId="archive" fill="#0ea5e9" maxBarSize={dense ? 16 : 32} />
          <Bar
            dataKey="contracts"
            name="合同"
            stackId="archive"
            fill="#10b981"
            maxBarSize={dense ? 16 : 32}
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 趋势图悬浮提示：日期 + 发票/合同件数。 */
function TrendTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name?: string; value?: number; color?: string; payload?: DashboardTrendPoint }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const dateLabel = payload[0]?.payload?.date || label
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-body-sm shadow-soft">
      <p className="mb-1.5 text-ink-tertiary">{dateLabel}</p>
      <ul className="space-y-1">
        {payload.map((item) => (
          <li key={item.name} className="flex items-center justify-between gap-6">
            <span className="flex items-center gap-1.5 text-ink-secondary">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
              {item.name}
            </span>
            <span className="tabular-nums font-semibold text-ink">{item.value ?? 0}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-lg border border-line bg-surface" />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-xl border border-line bg-surface" />
    </div>
  )
}
