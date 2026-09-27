import type { ReactNode } from 'react'
import { Download, ExternalLink, Loader2, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn, formatCurrency, formatDate } from '@/lib/utils'
import type { Invoice } from '@/types'

import { STATUS_LABEL, STATUS_TONE, TYPE_LABEL, TYPE_TONE } from './invoiceMeta'

export interface InvoiceDetailDialogProps {
  /** 列表里点开的那一行；关闭时为 null */
  preview: Invoice | null
  /** 详情接口返回的完整记录 */
  invoice: Invoice | undefined
  loading: boolean
  fileUrl?: string
  fileLoading: boolean
  deleting: boolean
  onClose: () => void
  onRequestFile: () => void
  onRequestDelete: () => void
}

/**
 * 发票详情弹窗。
 * 用票面表格展示字段：标签列固定、数值列留白，金额单独成行，避免两列键值挤在一起。
 */
export function InvoiceDetailDialog({
  preview,
  invoice,
  loading,
  fileUrl,
  fileLoading,
  deleting,
  onClose,
  onRequestFile,
  onRequestDelete,
}: InvoiceDetailDialogProps) {
  const title = invoice?.invoice_title || preview?.invoice_title || '查看发票完整字段'

  return (
    <Dialog open={!!preview} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>发票详情</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-5 w-5 animate-spin text-ink-tertiary" />
          </div>
        ) : invoice ? (
          <InvoiceSheet invoice={invoice} />
        ) : (
          <div className="py-12 text-center text-body-sm text-ink-tertiary">
            未能加载发票详情
          </div>
        )}

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onRequestFile}
            disabled={fileLoading || !invoice}
          >
            {fileLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            获取下载链接
          </Button>
          {fileUrl && (
            <Button asChild variant="primary">
              <a href={fileUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4" />
                下载原件
              </a>
            </Button>
          )}
          {invoice && invoice.status !== 'deleted' && (
            <Button
              variant="danger"
              onClick={onRequestDelete}
              disabled={deleting}
            >
              <Trash2 className="h-4 w-4" />
              删除
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 空值用淡色横线占位，和有值的单元格保持同一行高。 */
function Dash() {
  return <span className="text-ink-muted">-</span>
}

/** 票面分区标题，横跨整行，把字段分成可扫读的块。 */
function SectionRow({ children }: { children: string }) {
  return (
    <tr className="border-b border-line last:border-b-0">
      <th
        colSpan={4}
        scope="colgroup"
        className="bg-surface-inset px-4 py-2 text-left text-label-sm font-semibold tracking-wide text-ink-secondary"
      >
        {children}
      </th>
    </tr>
  )
}

/** 标签单元格：固定宽度、浅底，和数值列拉开对比。 */
function LabelCell({ children }: { children: string }) {
  return (
    <th
      scope="row"
      className="w-32 whitespace-nowrap border-r border-line bg-canvas px-4 py-3.5 text-left align-middle text-body-sm font-medium text-ink-tertiary"
    >
      {children}
    </th>
  )
}

function ValueCell({
  children,
  colSpan = 1,
  /** 这一格右边还有标签列时，补一条分隔线 */
  split = false,
  className,
}: {
  children: ReactNode
  colSpan?: number
  split?: boolean
  className?: string
}) {
  return (
    <td
      colSpan={colSpan}
      className={cn(
        'min-w-0 px-4 py-3.5 align-middle text-body-md text-ink',
        split && 'border-r border-line',
        className,
      )}
    >
      {children}
    </td>
  )
}

/** 金额三列：不含税、税额、价税合计并排，合计用浅底强调。 */
function AmountBand({ invoice }: { invoice: Invoice }) {
  const cells = [
    { label: '不含税金额', value: formatCurrency(invoice.amount_excl_tax), emphasis: false },
    { label: '税额', value: formatCurrency(invoice.tax_amount), emphasis: false },
    { label: '价税合计', value: formatCurrency(invoice.amount_incl_tax), emphasis: true },
  ] as const

  return (
    <tr className="border-b border-line last:border-b-0">
      <td colSpan={4} className="p-0">
        <div className="grid grid-cols-3">
          {cells.map((cell) => (
            <div
              key={cell.label}
              className={cn(
                'border-r border-line px-4 py-4 last:border-r-0',
                cell.emphasis && 'bg-primary-tint',
              )}
            >
              <div className="text-label-sm font-medium text-ink-tertiary">{cell.label}</div>
              <div
                className={cn(
                  'mt-1.5 tabular-nums',
                  cell.emphasis
                    ? 'text-numeric-md text-ink'
                    : 'text-body-lg font-medium text-ink',
                )}
              >
                {cell.value}
              </div>
            </div>
          ))}
        </div>
      </td>
    </tr>
  )
}

/**
 * 单张发票的票面表格。
 * 四列：标签 / 值 / 标签 / 值。长字段横跨后三列，避免号码和公司名折行挤在窄列里。
 */
function InvoiceSheet({ invoice }: { invoice: Invoice }) {
  const typeKey = invoice.invoice_type

  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-white">
      <table className="w-full min-w-[640px] table-fixed border-collapse">
        <colgroup>
          <col className="w-32" />
          <col />
          <col className="w-32" />
          <col />
        </colgroup>
        <tbody>
          <SectionRow>票面信息</SectionRow>
          <tr className="border-b border-line">
            <LabelCell>发票抬头</LabelCell>
            <ValueCell colSpan={3} className="font-semibold">
              {invoice.invoice_title || <Dash />}
            </ValueCell>
          </tr>
          <tr className="border-b border-line">
            <LabelCell>发票号码</LabelCell>
            <ValueCell split className="font-mono break-all">
              {invoice.invoice_number || <Dash />}
            </ValueCell>
            <LabelCell>发票代码</LabelCell>
            <ValueCell className="font-mono break-all">
              {invoice.invoice_code || <Dash />}
            </ValueCell>
          </tr>
          <tr className="border-b border-line">
            <LabelCell>开票日期</LabelCell>
            <ValueCell split className="tabular-nums">
              {invoice.invoice_date || <Dash />}
            </ValueCell>
            <LabelCell>发票类型</LabelCell>
            <ValueCell>
              {typeKey ? (
                <Badge tone={TYPE_TONE[typeKey] || 'neutral'}>
                  {TYPE_LABEL[typeKey] || typeKey}
                </Badge>
              ) : (
                <Dash />
              )}
            </ValueCell>
          </tr>
          <tr className="border-b border-line">
            <LabelCell>状态</LabelCell>
            <ValueCell colSpan={3}>
              <Badge tone={STATUS_TONE[invoice.status] || 'neutral'}>
                {STATUS_LABEL[invoice.status] || invoice.status}
              </Badge>
            </ValueCell>
          </tr>

          <SectionRow>交易双方</SectionRow>
          <tr className="border-b border-line">
            <LabelCell>购买方</LabelCell>
            <ValueCell split className="break-words">
              {invoice.buyer || <Dash />}
            </ValueCell>
            <LabelCell>销售方</LabelCell>
            <ValueCell className="break-words">{invoice.seller || <Dash />}</ValueCell>
          </tr>
          <tr className="border-b border-line">
            <LabelCell>开票公司</LabelCell>
            <ValueCell colSpan={3} className="break-words">
              {invoice.company || <Dash />}
            </ValueCell>
          </tr>
          <tr className="border-b border-line">
            <LabelCell>纳税人识别号</LabelCell>
            <ValueCell colSpan={3} className="font-mono break-all">
              {invoice.tax_id || <Dash />}
            </ValueCell>
          </tr>

          <SectionRow>金额</SectionRow>
          <AmountBand invoice={invoice} />

          <SectionRow>其他</SectionRow>
          <tr className="border-b border-line">
            <LabelCell>备注</LabelCell>
            <ValueCell colSpan={3} className="whitespace-pre-wrap break-words">
              {invoice.remark || <Dash />}
            </ValueCell>
          </tr>
          <tr>
            <LabelCell>归档时间</LabelCell>
            <ValueCell split className="tabular-nums text-ink-secondary">
              {formatDate(invoice.created_at)}
            </ValueCell>
            <LabelCell>文件指纹</LabelCell>
            <ValueCell className="font-mono text-body-sm break-all text-ink-secondary">
              {invoice.file_hash || <Dash />}
            </ValueCell>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
