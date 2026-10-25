import { useState } from 'react'
import { BookOpen, ExternalLink, Globe } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { WebSource } from '@/types'

/** 是否为企业制度来源。 */
function isPolicySource(source: WebSource): boolean {
  return source.source_kind === 'policy' || source.url.startsWith('kb://')
}

interface Props {
  sources: WebSource[]
  /** 角标点击时高亮对应来源项（Task 8 cite） */
  highlightIndex?: number | null
  /** 受控展开；未传时组件内部 toggle */
  expanded?: boolean
  onExpandedChange?: (open: boolean) => void
  className?: string
}

/** 解析 favicon 用的域名，优先 favicon_host。 */
function faviconDomain(source: WebSource): string {
  if (source.favicon_host) return source.favicon_host
  try {
    return new URL(source.url).hostname
  } catch {
    return ''
  }
}

/** 预览条 favicon；加载失败时显示 Globe 占位。 */
function SourceFaviconPreview({ source }: { source: WebSource }) {
  const [failed, setFailed] = useState(false)
  const domain = faviconDomain(source)

  if (!domain || failed) {
    return (
      <Globe
        aria-hidden
        className="-ml-1 h-4 w-4 rounded-full border border-white bg-canvas text-ink-tertiary first:ml-0"
      />
    )
  }

  return (
    <img
      alt=""
      src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`}
      className="-ml-1 h-4 w-4 rounded-full border border-white bg-canvas first:ml-0"
      onError={() => setFailed(true)}
    />
  )
}

/**
 * DeepSeek-style search sources strip: count + favicon preview, expandable list.
 * DeepSeek 风格：搜索到 N 个网页 + favicon；可展开列表。
 */
export function SearchSourcesBar({
  sources,
  highlightIndex = null,
  expanded,
  onExpandedChange,
  className,
}: Props) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = expanded ?? internalOpen
  const setOpen = onExpandedChange ?? setInternalOpen

  if (!sources.length) return null

  const policyCount = sources.filter(isPolicySource).length
  const webCount = sources.length - policyCount
  const label =
    policyCount > 0 && webCount > 0
      ? `找到 ${policyCount} 条制度与 ${webCount} 个网页`
      : policyCount > 0
        ? `找到 ${policyCount} 条企业制度`
        : `搜索到 ${webCount} 个网页`

  const preview = sources.slice(0, 8)
  const extra = sources.length - preview.length

  return (
    <div className={cn('mb-2', className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-body-sm text-ink-secondary transition-colors hover:text-ink"
        aria-expanded={open}
      >
        <span>{label}</span>
        <span className="flex items-center">
          {preview.map((s) =>
            isPolicySource(s) ? (
              <BookOpen
                key={`p-${s.index}`}
                aria-hidden
                className="-ml-1 h-4 w-4 rounded-full border border-white bg-canvas text-ink-tertiary first:ml-0"
              />
            ) : (
              <SourceFaviconPreview key={s.index} source={s} />
            ),
          )}
          {extra > 0 && <span className="ml-1 text-ink-tertiary">+{extra}</span>}
        </span>
      </button>
      {open && (
        <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-md border border-line bg-canvas p-2">
          {sources.map((s) => {
            const policy = isPolicySource(s)
            const subtitle = policy
              ? [s.section_path, s.doc_id ? `文档 ${s.doc_id.slice(0, 8)}…` : '']
                  .filter(Boolean)
                  .join(' · ') || '企业知识库'
              : s.favicon_host || s.url
            const rowClass = cn(
              'flex items-start gap-2 rounded px-1.5 py-1 text-body-sm transition-colors hover:bg-surface',
              highlightIndex === s.index && 'bg-primary-tint',
            )
            const body = (
              <>
                {policy ? (
                  <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-tertiary" />
                ) : (
                  <Globe className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-tertiary" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-1 font-medium text-ink">
                    [{s.index}] {s.title}
                  </span>
                  <span className="block truncate text-ink-tertiary">{subtitle}</span>
                </span>
                {!policy && (
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-tertiary" />
                )}
              </>
            )
            return (
              <li key={`${s.source_kind || 'web'}-${s.index}`}>
                {policy ? (
                  <div className={rowClass} title={s.snippet || s.title}>
                    {body}
                  </div>
                ) : (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className={rowClass}
                  >
                    {body}
                  </a>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

