import type { ReactNode } from 'react'
import { Copy, Download, Loader2, Trash2 } from 'lucide-react'

import { Markdown } from '@/components/chat/Markdown'
import { RiskBadge } from '@/components/sidepanel/RiskBadge'
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
import type { Contract, Violation } from '@/types'

export interface ContractDetailDialogProps {
  /** 列表里点开的那一行；关闭时为 null */
  preview: Contract | null
  /** 详情接口返回的完整记录 */
  contract: Contract | undefined
  loading: boolean
  fileLoading: boolean
  deleting: boolean
  onClose: () => void
  /** 换取临时预签名 URL 并复制到剪贴板 */
  onCopyDownloadLink: () => void
  /** 换取临时 URL 后打开/下载原件 */
  onDownloadOriginal: () => void
  onRequestDelete: () => void
}

/**
 * 合同详情弹窗。
 * 字段用表格展示；审查摘要与违规项单独成块，便于扫读风险。
 */
export function ContractDetailDialog({
  preview,
  contract,
  loading,
  fileLoading,
  deleting,
  onClose,
  onCopyDownloadLink,
  onDownloadOriginal,
  onRequestDelete,
}: ContractDetailDialogProps) {
  const title = contract?.contract_name || preview?.contract_name || '查看合同完整字段'
  const canFile = Boolean(contract?.file_url)

  return (
    <Dialog open={!!preview} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>合同详情</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-5 w-5 animate-spin text-ink-tertiary" />
          </div>
        ) : contract ? (
          <ContractSheet contract={contract} />
        ) : (
          <div className="py-12 text-center text-body-sm text-ink-tertiary">
            未能加载合同详情
          </div>
        )}

        <DialogFooter>
          <Button
            variant="secondary"
            type="button"
            onClick={onCopyDownloadLink}
            disabled={fileLoading || !canFile}
            title="复制约 1 小时有效的临时下载链接"
          >
            {fileLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            获取下载链接
          </Button>
          <Button
            variant="primary"
            type="button"
            onClick={onDownloadOriginal}
            disabled={fileLoading || !canFile}
            title="下载合同原件"
          >
            {fileLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            下载原件
          </Button>
          {contract && contract.status !== 'deleted' && (
            <Button variant="danger" onClick={onRequestDelete} disabled={deleting}>
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

/** 分区标题，横跨整行。 */
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

/** 标签单元格：固定宽度、浅底。 */
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

/** 合同字段表 + 审查结果。 */
function ContractSheet({ contract }: { contract: Contract }) {
  const review = contract.review_result
  const violations = (review?.violations || []) as Violation[]

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full min-w-[640px] table-fixed border-collapse">
          <colgroup>
            <col className="w-32" />
            <col />
            <col className="w-32" />
            <col />
          </colgroup>
          <tbody>
            <SectionRow>基本信息</SectionRow>
            <tr className="border-b border-line">
              <LabelCell>合同名称</LabelCell>
              <ValueCell colSpan={3} className="font-semibold">
                {contract.contract_name || <Dash />}
              </ValueCell>
            </tr>
            <tr className="border-b border-line">
              <LabelCell>合同编号</LabelCell>
              <ValueCell split className="font-mono break-all">
                {contract.contract_no || <Dash />}
              </ValueCell>
              <LabelCell>风险等级</LabelCell>
              <ValueCell>
                <RiskBadge level={contract.risk_level} />
              </ValueCell>
            </tr>
            <tr className="border-b border-line">
              <LabelCell>甲方</LabelCell>
              <ValueCell split className="break-words">
                {contract.party_a || <Dash />}
              </ValueCell>
              <LabelCell>乙方</LabelCell>
              <ValueCell className="break-words">{contract.party_b || <Dash />}</ValueCell>
            </tr>
            <tr className="border-b border-line">
              <LabelCell>合同金额</LabelCell>
              <ValueCell split className="tabular-nums font-semibold">
                {formatCurrency(contract.amount)}
              </ValueCell>
              <LabelCell>签订日期</LabelCell>
              <ValueCell className="tabular-nums">
                {formatDate(contract.sign_date) || contract.sign_date || <Dash />}
              </ValueCell>
            </tr>
            <tr className="border-b border-line">
              <LabelCell>生效开始</LabelCell>
              <ValueCell split className="tabular-nums">
                {formatDate(contract.effective_start) || contract.effective_start || <Dash />}
              </ValueCell>
              <LabelCell>生效结束</LabelCell>
              <ValueCell className="tabular-nums">
                {formatDate(contract.effective_end) || contract.effective_end || <Dash />}
              </ValueCell>
            </tr>
            <tr className="border-b border-line">
              <LabelCell>关键条款</LabelCell>
              <ValueCell colSpan={3} className="whitespace-pre-wrap break-words">
                {contract.key_clauses || <Dash />}
              </ValueCell>
            </tr>
            <tr>
              <LabelCell>归档时间</LabelCell>
              <ValueCell split className="tabular-nums text-ink-secondary">
                {formatDate(contract.created_at)}
              </ValueCell>
              <LabelCell>文件指纹</LabelCell>
              <ValueCell className="font-mono text-body-sm break-all text-ink-secondary">
                {contract.file_hash || <Dash />}
              </ValueCell>
            </tr>
          </tbody>
        </table>
      </div>

      {violations.length > 0 && (
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-headline-sm font-semibold text-ink">违规项</h3>
            <Badge tone="danger">{violations.length} 项</Badge>
          </div>
          <div className="space-y-2">
            {violations.map((v, i) => (
              <div
                key={`${v.clause}-${i}`}
                className="rounded-md border border-danger-border bg-danger-tint p-3 space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-body-md font-semibold text-ink">{v.clause || '未命名条款'}</span>
                  <RiskBadge level={v.severity} size="sm" />
                </div>
                <p className="text-body-sm text-ink-secondary">{v.issue || '-'}</p>
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
    </div>
  )
}
