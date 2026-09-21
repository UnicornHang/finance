import {
  CircleDollarSign,
  FileText,
  Receipt,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { StatCard, SectionHeader } from '@/components/ui/stat'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { RiskBadge } from '@/components/sidepanel/RiskBadge'
import { formatCurrency, formatDate } from '@/lib/utils'

/**
 * 首页看板
 * - 顶部 KPI 4 联
 * - 中部: 归档趋势图 (mocked bars) + 最近风险合同
 * - 底部: 业务进度 (用户/会话活跃度)
 */
export function Dashboard() {
  return (
    <div className="space-y-8">
      <SectionHeader
        title="数据概览"
        description="实时跟踪财务归档、合同审查与制度问答的关键指标"
      />

      {/* KPI Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="今日归档"
          value="24"
          suffix="张"
          delta={12.4}
          tone="success"
          deltaLabel="较昨日"
          icon={<Receipt className="h-3.5 w-3.5" />}
        />
        <StatCard
          label="本月发票总额"
          value="¥1,284,560"
          delta={-3.2}
          tone="danger"
          deltaLabel="较上月"
          icon={<CircleDollarSign className="h-3.5 w-3.5" />}
        />
        <StatCard
          label="本月合同"
          value="18"
          suffix="份"
          delta={8.7}
          tone="success"
          deltaLabel="较上月"
          icon={<FileText className="h-3.5 w-3.5" />}
        />
        <StatCard
          label="高风险合同"
          value="3"
          suffix="份"
          delta={50.0}
          tone="danger"
          deltaLabel="需关注"
          icon={<ShieldAlert className="h-3.5 w-3.5" />}
        />
      </div>

      {/* 趋势 + 风险 */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>近 7 天归档趋势</CardTitle>
                <CardDescription>发票与合同归档量</CardDescription>
              </div>
              <Badge tone="primary" dot>
                <TrendingUp className="h-3 w-3" />
                上升 8.4%
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <ChartPlaceholder />
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
              <span>更新时间 {formatDate(new Date().toISOString())}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>风险合同</CardTitle>
            <CardDescription>需立即处理的高风险合同</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <RiskItem title="设备采购合同 #2024-018" amount={580000} level="high" />
            <RiskItem title="外包服务协议 #2024-021" amount={120000} level="high" />
            <RiskItem title="软件订阅合同 #2024-035" amount={42000} level="medium" />
          </CardContent>
        </Card>
      </div>

      {/* 活跃度 + 检索 */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>本月活跃用户</CardTitle>
            <CardDescription>登录 / 上传 / 问答</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              <ActivityItem label="活跃用户" value="42" suffix="人" />
              <ActivityItem label="上传发票" value="286" suffix="张" />
              <ActivityItem label="制度问答" value="1,024" suffix="次" />
              <ActivityItem label="合同审查" value="18" suffix="份" />
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>财务摘要</CardTitle>
            <CardDescription>本月已归档凭证</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <SummaryRow label="不含税总额" value={formatCurrency(1145600)} />
            <SummaryRow label="税额合计" value={formatCurrency(138960)} />
            <SummaryRow label="进项税额" value={formatCurrency(92540)} />
            <div className="my-2 h-px bg-line-subtle" />
            <SummaryRow label="净入库" value={formatCurrency(1284560)} bold />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>知识库</CardTitle>
            <CardDescription>RAG 检索就绪</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Stat label="文档总数" value="86" />
            <Stat label="向量块数" value="3,420" />
            <Stat label="本月检索" value="5,128" />
            <div className="rounded-md border border-success-border bg-success-tint px-3 py-2 text-body-sm text-success">
              ✓ 所有文档均已索引完成
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/* ========================= 子组件 ========================= */

function RiskItem({
  title,
  amount,
  level,
}: {
  title: string
  amount: number
  level: 'high' | 'medium' | 'low'
}) {
  return (
    <div className="flex items-center justify-between rounded-md border border-line bg-canvas px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-body-md font-semibold text-ink">{title}</p>
        <p className="text-label-sm text-ink-tertiary tabular-nums">
          ¥ {amount.toLocaleString('zh-CN')}
        </p>
      </div>
      <RiskBadge level={level} />
    </div>
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
      <span
        className={cn(
          'tabular-nums',
          bold ? 'text-numeric-md font-semibold text-ink' : 'text-ink',
        )}
      >
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

function ChartPlaceholder() {
  // mock 7-day bars - 干净，极简风格，无重投影
  const data = [
    { d: '周一', v: 18 },
    { d: '周二', v: 24 },
    { d: '周三', v: 16 },
    { d: '周四', v: 28 },
    { d: '周五', v: 32 },
    { d: '周六', v: 12 },
    { d: '周日', v: 22 },
  ]
  const max = Math.max(...data.map((d) => d.v))

  return (
    <div className="flex h-44 items-end gap-3 px-2">
      {data.map((d) => {
        const heightPct = (d.v / max) * 100
        return (
          <div key={d.d} className="flex flex-1 flex-col items-center gap-2">
            <div className="flex h-full w-full items-end">
              <div
                className="w-full rounded-t bg-primary/15 hover:bg-primary/30 transition-colors relative"
                style={{ height: `${heightPct}%` }}
              >
                <div className="absolute inset-x-0 top-0 h-1 rounded-t bg-primary" />
              </div>
            </div>
            <span className="text-label-sm text-ink-tertiary">{d.d}</span>
          </div>
        )
      })}
    </div>
  )
}