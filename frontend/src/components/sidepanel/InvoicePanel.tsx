import { useState } from 'react'
import { FileSpreadsheet, Receipt, RotateCw } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'

import { Button } from '@/components/ui/button'
import { Input, Select, Textarea } from '@/components/ui/input'
import { SidePanel, Field } from '@/components/ui/surface'
import { Badge } from '@/components/ui/badge'
import { useUIStore } from '@/stores/uiStore'
import { invoiceSchema, type InvoiceInput } from '@/lib/validators'
import { formatCurrency } from '@/lib/utils'

export function InvoicePanel() {
  const { sidePanelOpen, sidePanelData, closeSidePanel } = useUIStore()
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<InvoiceInput>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: sidePanelData || {},
  })

  if (!sidePanelOpen || !sidePanelData) return null

  const onSubmit = async (data: InvoiceInput) => {
    setSubmitting(true)
    try {
      // TODO: 调用 invoiceApi.archive
      console.log('archive:', data)
      closeSidePanel()
    } finally {
      setSubmitting(false)
    }
  }

  const amountIncl = form.watch('amount_incl_tax')

  return (
    <SidePanel
      open={sidePanelOpen}
      onClose={closeSidePanel}
      icon={<Receipt className="h-4 w-4" />}
      title="发票识别结果"
      subtitle="AI 智能提取 · 请核对后归档"
      width={560}
      footer={
        <>
          <Button variant="ghost" size="md">
            <RotateCw className="h-4 w-4" />
            重新识别
          </Button>
          <div className="flex-1" />
          <Button variant="secondary" onClick={closeSidePanel}>
            取消
          </Button>
          <Button onClick={form.handleSubmit(onSubmit)} disabled={submitting}>
            {submitting ? '归档中...' : '确定归档'}
          </Button>
        </>
      }
    >
      <form className="space-y-5">
        {/* 顶部信息条 */}
        <div className="flex items-center justify-between rounded-md border border-line-subtle bg-canvas px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded bg-primary-tint text-primary">
              <FileSpreadsheet className="h-4 w-4" />
            </div>
            <div>
              <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
                识别置信度
              </p>
              <p className="text-numeric-md font-semibold text-ink tabular-nums">
                98.2%
              </p>
            </div>
          </div>
          <Badge tone="success" dot>
            字段完整
          </Badge>
        </div>

        {/* 抬头 / 销售方 */}
        <div className="grid grid-cols-2 gap-4">
          <Field label="发票抬头" error={form.formState.errors.invoice_title?.message}>
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
          <Input {...form.register('tax_id')} placeholder="18 位税号" className="font-mono" />
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
          <Input type="date" {...form.register('invoice_date')} />
        </Field>

        {/* 金额三栏 - 财务核心数据 */}
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
          {typeof amountIncl === 'number' && (
            <p className="text-body-sm text-ink-tertiary">
              含税合计 <span className="font-semibold text-ink tabular-nums">{formatCurrency(amountIncl)}</span>
            </p>
          )}
        </div>

        <Field label="发票类型">
          <Select {...form.register('invoice_type')}>
            <option value="">请选择</option>
            <option value="special">增值税专用发票</option>
            <option value="general">增值税普通发票</option>
            <option value="electronic">电子发票</option>
          </Select>
        </Field>

        <Field label="备注">
          <Textarea rows={3} {...form.register('remark')} placeholder="可填写备注信息" />
        </Field>
      </form>
    </SidePanel>
  )
}