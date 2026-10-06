import type { InvoiceInput } from '@/lib/validators'
import type { InvoiceSidePanelData } from '@/stores/uiStore'

/** 从 sidePanelData 中抽取可填入表单的发票字段。 */
export function pickInvoiceFields(data: InvoiceSidePanelData): Partial<InvoiceInput> {
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
export function calcConfidence(invoice: InvoiceInput | undefined): number | null {
  if (!invoice) return null
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
