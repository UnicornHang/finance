import { FileText, RotateCw, ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SidePanel, Field } from '@/components/ui/surface'
import { Badge } from '@/components/ui/badge'
import { RiskBadge } from './RiskBadge'
import { useUIStore } from '@/stores/uiStore'
import { formatCurrency, formatDate } from '@/lib/utils'

export function ContractPanel() {
  const { sidePanelOpen, sidePanelData, closeSidePanel } = useUIStore()

  if (!sidePanelOpen || !sidePanelData) return null

  const review = sidePanelData.review_result
  const violationCount = review?.violations?.length || 0

  return (
    <SidePanel
      open={sidePanelOpen}
      onClose={closeSidePanel}
      icon={<FileText className="h-4 w-4" />}
      title="合同审查结果"
      subtitle="RAG 规则匹配 · 风险等级标注"
      width={560}
      footer={
        <>
          <Button variant="ghost" size="md">
            <RotateCw className="h-4 w-4" />
            重新审查
          </Button>
          <div className="flex-1" />
          <Button variant="secondary" onClick={closeSidePanel}>
            取消
          </Button>
          <Button>确定归档</Button>
        </>
      }
    >
      <div className="space-y-6">
        {/* 顶部摘要卡 */}
        <div className="flex items-center justify-between rounded-md border border-line-subtle bg-canvas px-4 py-3">
          <div>
            <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
              风险评估
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <RiskBadge level={sidePanelData.risk_level} />
              <span className="text-body-sm text-ink-tertiary">
                检出 <span className="font-semibold text-ink tabular-nums">{violationCount}</span> 项风险
              </span>
            </div>
          </div>
          {review?.summary && (
            <Badge tone={violationCount > 0 ? 'warning' : 'success'} dot>
              {violationCount > 0 ? '需关注' : '审查通过'}
            </Badge>
          )}
        </div>

        {/* 基本信息 */}
        <section className="space-y-4">
          <Field label="合同名称">
            <Input
              value={sidePanelData.contract_name || ''}
              readOnly
              className="bg-canvas"
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="甲方">
              <Input value={sidePanelData.party_a || ''} readOnly className="bg-canvas" />
            </Field>
            <Field label="乙方">
              <Input value={sidePanelData.party_b || ''} readOnly className="bg-canvas" />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field label="签订日期">
              <Input
                value={formatDate(sidePanelData.sign_date)}
                readOnly
                className="bg-canvas"
              />
            </Field>
            <Field label="合同金额">
              <Input
                value={formatCurrency(sidePanelData.amount)}
                readOnly
                className="bg-canvas tabular-nums"
              />
            </Field>
          </div>
        </section>

        {/* 违规项 */}
        {review?.violations && review.violations.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-headline-sm font-semibold text-ink">
                <ShieldAlert className="h-4 w-4 text-danger" />
                违规项
              </h3>
              <Badge tone="danger">{review.violations.length} 项</Badge>
            </div>
            <div className="space-y-2">
              {review.violations.map((v: any, i: number) => (
                <div
                  key={i}
                  className="rounded-md border border-danger-border bg-danger-tint p-3 space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-body-md font-semibold text-ink">
                      {v.clause}
                    </span>
                    <RiskBadge level={v.severity} size="sm" />
                  </div>
                  <p className="text-body-sm text-ink-secondary">{v.issue}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 审查摘要 */}
        {review?.summary && (
          <section className="space-y-2">
            <h3 className="text-headline-sm font-semibold text-ink">审查摘要</h3>
            <div className="rounded-md border border-line bg-surface-inset p-4 text-body-md text-ink-secondary leading-relaxed">
              {review.summary}
            </div>
          </section>
        )}
      </div>
    </SidePanel>
  )
}