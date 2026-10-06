import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FileText, Loader2, RotateCw, ShieldAlert, AlertCircle, X } from 'lucide-react'
import { toast } from 'sonner'

import { Markdown } from '@/components/chat/Markdown'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/surface'
import { Badge } from '@/components/ui/badge'
import { RiskBadge } from './RiskBadge'
import { contractApi } from '@/api/contract'
import { readApiMessage } from '@/lib/apiError'
import { useUIStore } from '@/stores/uiStore'
import { formatCurrency } from '@/lib/utils'

type ContractPanelData = {
  status?: 'processing' | 'ready' | string
  review_result?: { violations?: unknown[]; summary?: string; risk_level?: string }
  risk_level?: 'high' | 'medium' | 'low' | null
  contract_name?: string | null
  party_a?: string | null
  party_b?: string | null
  sign_date?: string | null
  amount?: number | null
  file_url?: string | null
  file_hash?: string | null
  chat_file_id?: string | null
  contract_id?: string | null
  id?: string | null
  /** pending=待确认归档；archived=已归档 */
  archive_status?: 'pending' | 'archived' | string | null
  message?: string
  reason?: string
}

/** 从审查摘要粗判风险，侧栏没带 risk_level 时用。 */
function guessRiskLevel(data: ContractPanelData): 'high' | 'medium' | 'low' {
  if (data.risk_level === 'high' || data.risk_level === 'medium' || data.risk_level === 'low') {
    return data.risk_level
  }
  const nested = data.review_result?.risk_level
  if (nested === 'high' || nested === 'medium' || nested === 'low') return nested
  const summary = data.review_result?.summary || ''
  if (/高风险|极高风险/.test(summary)) return 'high'
  if (/中风险/.test(summary)) return 'medium'
  return 'low'
}

/** 合同面板：根据 sidePanelData 内容显示处理中态 / 审查结果，并支持确定归档。 */
export function ContractPanel() {
  const { sidePanelData, closeSidePanel, clearSidePanel, openSidePanel } = useUIStore()
  const queryClient = useQueryClient()
  const [submitting, setSubmitting] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const data = (sidePanelData ?? null) as ContractPanelData | null

  const [contractName, setContractName] = useState('')
  const [partyA, setPartyA] = useState('')
  const [partyB, setPartyB] = useState('')
  const [signDate, setSignDate] = useState('')
  const [amountText, setAmountText] = useState('')

  useEffect(() => {
    if (!data || data.status === 'processing') return
    setContractName(data.contract_name || '')
    setPartyA(data.party_a || '')
    setPartyB(data.party_b || '')
    setSignDate((data.sign_date || '').slice(0, 10))
    setAmountText(
      data.amount == null || Number.isNaN(Number(data.amount)) ? '' : String(data.amount),
    )
    setSubmitError(null)
  }, [
    data?.contract_name,
    data?.party_a,
    data?.party_b,
    data?.sign_date,
    data?.amount,
    data?.file_hash,
    data?.status,
  ])

  if (!data) return null

  const isProcessing = data.status === 'processing'
  const review = data.review_result
  const violationCount = review?.violations?.length || 0
  const pipelineNotImplemented =
    data.status === 'not_found' || data.reason === 'contract_parse_pipeline_not_implemented'
  const riskLevel = guessRiskLevel(data)
  // contract_id 在审查后就会有（pending_review）；真正已归档看 archive_status / status
  const alreadyArchived =
    data.archive_status === 'archived' || data.status === 'active'

  const onArchive = async () => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const amountRaw = amountText.trim().replace(/,/g, '')
      const amount = amountRaw ? Number(amountRaw) : null
      const fields = {
        contract_name: contractName.trim() || data.contract_name || null,
        party_a: partyA.trim() || null,
        party_b: partyB.trim() || null,
        sign_date: signDate.trim() || null,
        amount: amount != null && !Number.isNaN(amount) ? amount : null,
        risk_level: riskLevel,
        // 审查摘要只在识别时写入，确认归档不再回传，避免覆盖成脏数据
      }

      if (data.contract_id && !alreadyArchived) {
        // 主路径：pending_review → active
        await contractApi.confirm(data.contract_id, fields)
        toast.success('合同已归档')
      } else if (!data.contract_id) {
        // 兼容老会话：先写 pending，再确认（仍由用户这一次点击触发）
        const file_url = data.file_url || ''
        const file_hash = data.file_hash || ''
        if (!file_url || !file_hash) {
          const msg = '缺少文件信息，无法归档。请重新上传合同后再试。'
          setSubmitError(msg)
          toast.error(msg)
          return
        }
        const pending = await contractApi.archive({
          ...fields,
          review_result: review ?? null,
          file_url,
          file_hash,
          chat_file_id: data.chat_file_id || undefined,
        })
        await contractApi.confirm(pending.id, fields)
        toast.success('合同已归档')
      } else {
        toast.info('合同已归档，无需重复确认')
        return
      }

      queryClient.invalidateQueries({ queryKey: ['contracts'] })
      clearSidePanel()
    } catch (err: unknown) {
      const msg = readApiMessage(err) || '归档失败'
      setSubmitError(msg)
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const contractId = data.contract_id || data.id || null

  /** 用同一份原件再跑审查，覆盖摘要和概览字段。 */
  const onRereview = async () => {
    if (!contractId) {
      toast.error('缺少合同记录，请重新上传后再审查')
      return
    }
    setRetrying(true)
    setSubmitError(null)
    try {
      const row = await contractApi.reReview(contractId)
      const archiveStatus =
        row.status === 'active' || row.archive_status === 'archived'
          ? 'archived'
          : row.status === 'pending_review'
            ? 'pending'
            : row.status
      openSidePanel('contract', {
        ...row,
        status: 'ready',
        contract_id: row.id,
        archive_status: archiveStatus,
        chat_file_id: data.chat_file_id || null,
        file_url: row.file_url || data.file_url,
        file_hash: row.file_hash || data.file_hash,
      })
      toast.success('已按原件重新审查，请核对结果')
    } catch (err: unknown) {
      const msg = readApiMessage(err) || '重新审查失败'
      setSubmitError(msg)
      toast.error(msg)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <aside className="flex h-full w-full flex-col bg-surface" data-slot="contract-panel">
      <header className="flex items-center justify-between border-b border-line px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-primary-tint text-primary">
            <FileText className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-headline-sm font-semibold text-ink leading-tight">
              {isProcessing
                ? '正在解析合同'
                : pipelineNotImplemented
                  ? '合同识别流水线未实装'
                  : '合同审查结果'}
            </h2>
            <p className="text-body-sm text-ink-tertiary leading-tight">
              {isProcessing
                ? 'PDF 解析与合规审查中'
                : pipelineNotImplemented
                  ? 'Phase B TODO'
                  : alreadyArchived
                    ? '已归档'
                    : '请核对字段后确认归档'}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          type="button"
          onClick={closeSidePanel}
          aria-label="关闭合同面板"
        >
          <X className="h-4 w-4" />
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {isProcessing && (
          <div className="flex flex-col items-center justify-center gap-4 py-10">
            <Loader2 className="h-12 w-12 animate-spin text-primary/40" />
            <p className="text-body-md font-medium text-ink">AI 正在解析合同…</p>
            <p className="text-body-sm text-ink-tertiary">
              下载 PDF → 文本提取 → 合规审查
            </p>
          </div>
        )}

        {pipelineNotImplemented && (
          <div className="rounded-md border border-warning/30 bg-warning-tint p-4 text-body-md text-warning">
            <p className="font-semibold">合同识别流水线尚未实装</p>
            <p className="mt-1 text-body-sm text-ink-secondary">
              {data.message ??
                '上传动作已记录（文件已落到 MinIO contracts 桶），PDF 解析与合规审查将在 Phase B 完成。'}
            </p>
          </div>
        )}

        {!isProcessing && !pipelineNotImplemented && (
          <div className="space-y-6">
            <div className="flex items-center justify-between rounded-md border border-line-subtle bg-canvas px-4 py-3">
              <div>
                <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
                  风险评估
                </p>
                <div className="mt-1.5 flex items-center gap-2">
                  <RiskBadge level={riskLevel} />
                  <span className="text-body-sm text-ink-tertiary">
                    检出{' '}
                    <span className="font-semibold text-ink tabular-nums">{violationCount}</span>{' '}
                    项风险
                  </span>
                </div>
              </div>
              {review?.summary && (
                <Badge tone={riskLevel === 'low' && violationCount === 0 ? 'success' : 'warning'} dot>
                  {riskLevel === 'high' ? '高风险' : riskLevel === 'medium' ? '需关注' : '审查通过'}
                </Badge>
              )}
            </div>

            <section className="space-y-4">
              <Field label="合同名称">
                <Input
                  value={contractName}
                  onChange={(e) => setContractName(e.target.value)}
                  className="bg-canvas"
                />
              </Field>

              <div className="grid grid-cols-2 gap-4">
                <Field label="甲方">
                  <Input
                    value={partyA}
                    onChange={(e) => setPartyA(e.target.value)}
                    className="bg-canvas"
                  />
                </Field>
                <Field label="乙方">
                  <Input
                    value={partyB}
                    onChange={(e) => setPartyB(e.target.value)}
                    className="bg-canvas"
                  />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Field label="签订日期">
                  <Input
                    type="date"
                    value={signDate}
                    onChange={(e) => setSignDate(e.target.value)}
                    className="bg-canvas"
                  />
                </Field>
                <Field label="合同金额">
                  <Input
                    inputMode="decimal"
                    value={amountText}
                    onChange={(e) => setAmountText(e.target.value)}
                    placeholder={formatCurrency(data.amount) || '金额'}
                    className="bg-canvas tabular-nums"
                  />
                </Field>
              </div>
            </section>

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
                        <span className="text-body-md font-semibold text-ink">{v.clause}</span>
                        <RiskBadge level={v.severity} size="sm" />
                      </div>
                      <p className="text-body-sm text-ink-secondary">{v.issue}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {review?.summary && (
              <section className="space-y-2">
                <h3 className="text-headline-sm font-semibold text-ink">审查摘要</h3>
                <div className="rounded-md border border-line bg-canvas px-4 py-3">
                  <Markdown
                    content={review.summary}
                    className="text-ink-secondary [&_h1]:text-ink [&_h2]:text-ink [&_h3]:text-ink [&_strong]:text-ink"
                  />
                </div>
              </section>
            )}

            {submitError && (
              <div className="rounded-md border border-danger/30 bg-danger-tint px-3 py-2 text-body-sm text-danger">
                {submitError}
              </div>
            )}
            {alreadyArchived && (
              <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-tint px-3 py-2 text-body-sm text-warning">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>这份合同已经归档了，无需再次确认归档</span>
              </div>
            )}
          </div>
        )}
      </div>

      <footer className="flex items-center gap-2 border-t border-line px-5 py-3">
        {!alreadyArchived && (
          <Button
            variant="ghost"
            size="md"
            type="button"
            disabled={retrying || submitting || isProcessing || pipelineNotImplemented || !contractId}
            onClick={() => void onRereview()}
            title={contractId ? '按原件重新审查' : '缺少合同记录，请重新上传'}
          >
            {retrying ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
            {retrying ? '审查中...' : '重新审查'}
          </Button>
        )}
        <div className="flex-1" />
        <Button variant="secondary" onClick={closeSidePanel} type="button">
          {alreadyArchived ? '关闭' : '取消'}
        </Button>
        {!alreadyArchived && (
          <Button
            type="button"
            disabled={isProcessing || pipelineNotImplemented || submitting || retrying}
            onClick={() => void onArchive()}
          >
            {submitting ? '归档中...' : '确定归档'}
          </Button>
        )}
      </footer>
    </aside>
  )
}
