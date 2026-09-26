import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  FileSpreadsheet,
  Loader2,
  Receipt,
  RotateCw,
  X,
} from 'lucide-react'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { DatePicker } from '@/components/ui/date-picker'
import { Input, Textarea } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Field } from '@/components/ui/surface'
import { Badge } from '@/components/ui/badge'
import { useUIStore, type InvoiceSidePanelData } from '@/stores/uiStore'
import { invoiceApi } from '@/api/invoice'
import { invoiceSchema, type InvoiceInput } from '@/lib/validators'
import { formatCurrency } from '@/lib/utils'

const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 30 // ~60s

/** 从 sidePanelData 中抽取可填入表单的发票字段。 */
function pickInvoiceFields(data: InvoiceSidePanelData): Partial<InvoiceInput> {
  const source = data as Partial<InvoiceInput> & Record<string, unknown>
  const date = typeof source.invoice_date === 'string' ? source.invoice_date.slice(0, 10) : source.invoice_date
  return {
    invoice_title: source.invoice_title ?? '',
    company: source.company ?? '',
    tax_id: source.tax_id ?? '',
    invoice_code: source.invoice_code ?? '',
    invoice_number: source.invoice_number ?? '',
    invoice_date: date ?? '',
    amount_excl_tax: source.amount_excl_tax ?? undefined,
    tax_amount: source.tax_amount ?? undefined,
    amount_incl_tax: source.amount_incl_tax ?? undefined,
    invoice_type: source.invoice_type ?? '',
    seller: source.seller ?? '',
    buyer: source.buyer ?? '',
    remark: source.remark ?? '',
  }
}

/** 处理中态平均置信度（按已有字段计算）。 */
function calcConfidence(invoice: InvoiceInput | undefined): number | null {
  if (!invoice) return null
  // 简化：必填字段填了几个
  const required: (keyof InvoiceInput)[] = [
    'invoice_title',
    'invoice_number',
    'amount_incl_tax',
    'invoice_date',
  ]
  const filled = required.filter((k) => {
    const v = invoice[k]
    return v !== undefined && v !== null && v !== ''
  }).length
  return filled / required.length
}

export function InvoicePanel() {
  const { sidePanelData, closeSidePanel, openSidePanel } = useUIStore()
  const [submitting, setSubmitting] = useState(false)
  const [pollAttempts, setPollAttempts] = useState(0)
  const [pollError, setPollError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const data = (sidePanelData ?? null) as InvoiceSidePanelData | null

  const isProcessing =
    data !== null &&
    typeof data === 'object' &&
    'status' in data &&
    data.status === 'processing'

  const isReady =
    data !== null &&
    typeof data === 'object' &&
    'status' in data &&
    data.status === 'ready' &&
    'invoice_id' in data &&
    typeof (data as { invoice_id?: string }).invoice_id === 'string'

  const invoiceId =
    isReady && 'invoice_id' in data ? (data.invoice_id as string) : undefined

  const form = useForm<InvoiceInput>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: {},
  })

  // 识别中先打开侧栏，结果后到。defaultValues 不会随数据更新，必须 reset 才能填进输入框。
  useEffect(() => {
    if (!data || isProcessing) return
    form.reset(pickInvoiceFields(data))
  }, [data, isProcessing, form])

  // OCR 完成 → 轮询发票入库状态
  useEffect(() => {
    if (!isProcessing || !data || !('file_hash' in data)) return
    const fileHash = (data as { file_hash: string }).file_hash
    let cancelled = false
    let attempts = 0
    setPollError(null)

    const tick = async () => {
      if (cancelled) return
      attempts += 1
      try {
        const r = await invoiceApi.previewByHash(fileHash)
        if (cancelled) return
        if (r.status === 'ready' && r.invoice) {
          setPollAttempts(attempts)
          // 把 ready 数据塞回 sidePanelData，触发 isReady 分支
          // 注意：r.invoice.status 是原始 DB status（pending_review/active），
          // 这里覆盖为 'ready' 表示「前端 UI 状态」而非入库状态
          // TODO(Phase A+ 后续清理): 用 UI-state 枚举替代字符串复用
          openSidePanel('invoice', {
            ...r.invoice,
            status: 'ready',
            invoice_id: r.invoice.id,
          })
          toast.success('发票字段识别完成，请核对后归档')
          return
        }
        if (r.status === 'not_found' || attempts >= POLL_MAX_ATTEMPTS) {
          setPollAttempts(attempts)
          setPollError(
            attempts >= POLL_MAX_ATTEMPTS
              ? '识别超时，请稍后到「档案」页查看或重新上传'
              : '识别失败，请重试',
          )
          return
        }
        setPollAttempts(attempts)
        setTimeout(tick, POLL_INTERVAL_MS)
      } catch (err) {
        if (cancelled) return
        setPollError(err instanceof Error ? err.message : '轮询失败')
      }
    }

    tick()
    return () => {
      cancelled = true
    }
  }, [isProcessing, data, openSidePanel])

  if (!data) return null

  const onSubmit = async (formData: InvoiceInput) => {
    setSubmitting(true)
    try {
      if (isReady && invoiceId) {
        // ready 状态：编辑 + 确认一步到位（pending_review → active）
        await invoiceApi.confirm(invoiceId, formData)
        toast.success('发票已归档')
      } else {
        // 兼容老调用 / 直接 JSON 入库
        const file_url =
          (data as { file_url?: string }).file_url || ''
        const file_hash =
          (data as { file_hash?: string }).file_hash || ''
        await invoiceApi.archive({ ...formData, file_url, file_hash })
        toast.success('已归档')
      }
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      closeSidePanel()
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null
      toast.error(msg || (err instanceof Error ? err.message : '归档失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const amountIncl = form.watch('amount_incl_tax')

  // 三栏右栏外层（持久 aside，由 pages/Chat.tsx 条件渲染挂载）
  return (
    <aside className="flex h-full w-full flex-col bg-surface" data-slot="invoice-panel">
      {/* 顶部 header */}
      <header className="flex items-center justify-between border-b border-line px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-primary-tint text-primary">
            <Receipt className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-headline-sm font-semibold text-ink leading-tight">
              {isProcessing ? '正在识别发票' : '发票识别结果'}
            </h2>
            <p className="text-body-sm text-ink-tertiary leading-tight">
              {isProcessing
                ? 'AI 智能提取字段中'
                : isReady
                  ? 'AI 智能提取 · 请核对后归档'
                  : '手动归档'}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          type="button"
          onClick={closeSidePanel}
          aria-label="关闭发票面板"
        >
          <X className="h-4 w-4" />
        </Button>
      </header>

      {/* 中部 body */}
      <div className="flex-1 overflow-y-auto px-5 py-5">
        {isProcessing ? (
          <div className="flex flex-col items-center justify-center gap-4 py-10">
            <div className="relative flex h-16 w-16 items-center justify-center">
              <Loader2 className="h-16 w-16 animate-spin text-primary/30" />
              <Receipt className="absolute h-6 w-6 text-primary" />
            </div>
            <p className="text-body-md font-medium text-ink">AI 正在识别发票字段…</p>
            <p className="text-body-sm text-ink-tertiary tabular-nums">
              已尝试 {pollAttempts}/{POLL_MAX_ATTEMPTS} 次（约{' '}
              {Math.round((pollAttempts * POLL_INTERVAL_MS) / 1000)}s）
            </p>
          </div>
        ) : null}

        {isProcessing && pollError && (
          <div className="mt-5 flex items-start gap-2 rounded-md border border-danger/30 bg-danger-tint px-3 py-2 text-body-sm text-danger">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{pollError}</span>
          </div>
        )}

        {isProcessing && (
          <div className="mt-5 space-y-2">
            <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
              识别内容
            </p>
            <ul className="space-y-1.5 text-body-sm text-ink-tertiary">
              <li className="flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin" />
                解析发票代码与号码
              </li>
              <li className="flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin" />
                提取金额、税额与日期
              </li>
              <li className="flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin" />
                识别购销方与税号
              </li>
            </ul>
          </div>
        )}

        {!isProcessing && (
          <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
            {/* 顶部信息条 */}
            <div className="flex items-center justify-between rounded-md border border-line-subtle bg-canvas px-4 py-3">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded bg-primary-tint text-primary">
                  <FileSpreadsheet className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
                    字段完整度
                  </p>
                  <p className="text-numeric-md font-semibold text-ink tabular-nums">
                    {(() => {
                      const c = calcConfidence(form.getValues())
                      return c !== null ? `${Math.round(c * 100)}%` : '—'
                    })()}
                  </p>
                </div>
              </div>
              <Badge
                tone={
                  (() => {
                    const c = calcConfidence(form.getValues())
                    const pct = c !== null ? Math.round(c * 100) : null
                    return pct !== null && pct >= 75 ? 'success' : 'neutral'
                  })()
                }
                dot
              >
                {(() => {
                  const c = calcConfidence(form.getValues())
                  const pct = c !== null ? Math.round(c * 100) : null
                  return pct !== null && pct >= 75 ? '字段完整' : '请补全'
                })()}
              </Badge>
            </div>

            {/* 抬头 / 销售方 */}
            <div className="grid grid-cols-2 gap-4">
              <Field
                label="发票抬头"
                error={form.formState.errors.invoice_title?.message}
              >
                <Input {...form.register('invoice_title')} placeholder="购买方名称" />
              </Field>
              <Field label="销售方">
                <Input {...form.register('seller')} placeholder="开票公司" />
              </Field>
            </div>

            <Field label="购买方">
              <Input {...form.register('buyer')} placeholder="收票方" />
            </Field>

            {/* 税号 */}
            <Field label="纳税人识别号">
              <Input
                {...form.register('tax_id')}
                placeholder="18 位税号"
                className="font-mono"
              />
            </Field>

            {/* 代码 / 号码 */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="发票代码">
                <Input {...form.register('invoice_code')} className="font-mono" />
              </Field>
              <Field label="发票号码">
                <Input {...form.register('invoice_number')} className="font-mono" />
              </Field>
            </div>

            <Field label="开票日期">
              <Controller
                control={form.control}
                name="invoice_date"
                render={({ field }) => (
                  <DatePicker value={field.value} onChange={field.onChange} />
                )}
              />
            </Field>

            {/* 金额三栏 */}
            <div className="space-y-2">
              <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
                金额明细
              </p>
              <div className="grid grid-cols-3 gap-3 rounded-lg border border-line bg-surface-inset p-3">
                <Field label="不含税">
                  <Input
                    type="number"
                    step="0.01"
                    className="tabular-nums"
                    {...form.register('amount_excl_tax')}
                  />
                </Field>
                <Field label="税额">
                  <Input
                    type="number"
                    step="0.01"
                    className="tabular-nums"
                    {...form.register('tax_amount')}
                  />
                </Field>
                <Field label="含税合计">
                  <Input
                    type="number"
                    step="0.01"
                    className="tabular-nums border-primary/40 focus-visible:border-primary"
                    {...form.register('amount_incl_tax')}
                  />
                </Field>
              </div>
              {typeof amountIncl === 'number' && amountIncl > 0 && (
                <p className="text-body-sm text-ink-tertiary">
                  含税合计{' '}
                  <span className="font-semibold text-ink tabular-nums">
                    {formatCurrency(amountIncl)}
                  </span>
                </p>
              )}
            </div>

            <Field label="发票类型">
              <Controller
                control={form.control}
                name="invoice_type"
                render={({ field }) => (
                  <Select value={field.value || ''} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue placeholder="请选择发票类型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="special">增值税专用发票</SelectItem>
                      <SelectItem value="general">增值税普通发票</SelectItem>
                      <SelectItem value="electronic">电子发票</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </Field>

            <Field label="备注">
              <Textarea rows={3} {...form.register('remark')} placeholder="可填写备注信息" />
            </Field>

            {isReady && (
              <div className="flex items-center gap-2 rounded-md bg-success-tint px-3 py-2 text-body-sm text-success">
                <CheckCircle2 className="h-4 w-4" />
                <span>识别完成，点击「确定归档」即可保存到档案</span>
              </div>
            )}
          </form>
        )}
      </div>

      {/* 底部 footer（仅 ready 显示操作按钮） */}
      {!isProcessing && (
        <footer className="flex items-center gap-2 border-t border-line px-5 py-3">
          <Button variant="ghost" size="md" type="button">
            <RotateCw className="h-4 w-4" />
            重新识别
          </Button>
          <div className="flex-1" />
          <Button variant="secondary" onClick={closeSidePanel} type="button">
            取消
          </Button>
          <Button
            onClick={form.handleSubmit(onSubmit)}
            disabled={submitting}
            type="button"
          >
            {submitting ? '归档中...' : '确定归档'}
          </Button>
        </footer>
      )}
    </aside>
  )
}

