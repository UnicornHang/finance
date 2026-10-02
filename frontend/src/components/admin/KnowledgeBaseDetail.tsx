import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FileText, Layers } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Markdown } from '@/components/chat/Markdown'
import { InvoiceListPager } from '@/components/admin/InvoiceListPager'
import {
  KB_STATUS_LABEL,
  KB_STATUS_TONE,
  kbDocTypeLabel,
} from '@/components/admin/kbMeta'
import { kbApi } from '@/api/admin'
import { cn, formatDate } from '@/lib/utils'

const CHUNK_PAGE_SIZE = 5

type DetailTab = 'content' | 'chunks'

/** 知识库文档详情：中间全文/切分块 Tab，右侧元数据。 */
export function KnowledgeBaseDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<DetailTab>('content')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(CHUNK_PAGE_SIZE)

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ['kb-document', id],
    queryFn: () => kbApi.get(id!),
    enabled: Boolean(id),
  })

  useEffect(() => {
    setTab('content')
    setPage(1)
  }, [id])

  useEffect(() => {
    setPage(1)
  }, [pageSize, tab])

  const errMsg =
    (error as { response?: { data?: { message?: string } } })?.response?.data
      ?.message || '加载失败'

  const chunks = data?.chunks ?? []
  const pagedChunks = useMemo(() => {
    const start = (page - 1) * pageSize
    return chunks.slice(start, start + pageSize)
  }, [chunks, page, pageSize])

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4 overflow-hidden">
      {/* 顶栏：返回 + 标题 */}
      <div className="flex shrink-0 items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => navigate('/admin/kb')}
        >
          <ArrowLeft className="h-4 w-4" />
          返回列表
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-headline-sm font-semibold text-ink">
              {data?.title || (isFetching ? '加载中…' : '文档详情')}
            </h1>
            {data && (
              <Badge tone={KB_STATUS_TONE[data.status] || 'neutral'} dot>
                {KB_STATUS_LABEL[data.status] || data.status}
              </Badge>
            )}
          </div>
          {data && (
            <p className="mt-0.5 text-label-sm text-ink-tertiary">
              {kbDocTypeLabel(data.doc_type)} · {data.chunk_count} 块 · v
              {data.version}
            </p>
          )}
        </div>
      </div>

      {/* 主体：中间内容 + 右侧元数据 */}
      <div className="flex min-h-0 flex-1 gap-6 overflow-hidden">
        <Card className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 gap-1 border-b border-line-subtle bg-surface px-4 pt-3">
            <TabButton
              active={tab === 'content'}
              icon={<FileText className="h-3.5 w-3.5" />}
              label="全文"
              onClick={() => setTab('content')}
            />
            <TabButton
              active={tab === 'chunks'}
              icon={<Layers className="h-3.5 w-3.5" />}
              label={`切分块 (${chunks.length})`}
              onClick={() => setTab('chunks')}
            />
          </div>

          <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden p-0">
            {isFetching && (
              <p className="p-6 text-body-sm text-ink-tertiary">加载中…</p>
            )}
            {!isFetching && isError && (
              <div className="space-y-3 p-6">
                <p className="text-body-sm text-danger">{errMsg}</p>
                <Button asChild variant="secondary" size="sm">
                  <Link to="/admin/kb">返回知识库</Link>
                </Button>
              </div>
            )}
            {!isFetching && !isError && data && tab === 'content' && (
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                {data.content.trim() ? (
                  <Markdown content={data.content} className="text-ink" />
                ) : (
                  <p className="text-body-sm text-ink-tertiary">暂无正文</p>
                )}
              </div>
            )}
            {!isFetching && !isError && data && tab === 'chunks' && (
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {chunks.length === 0 ? (
                  <p className="p-6 text-body-sm text-ink-tertiary">
                    尚无切分块，请先完成索引
                  </p>
                ) : (
                  <>
                    <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
                      {pagedChunks.map((c) => (
                        <li
                          key={c.id}
                          className="rounded-md border border-line-subtle bg-canvas px-4 py-3"
                        >
                          <div className="mb-2 flex items-center gap-2 text-label-sm text-ink-tertiary">
                            <span className="rounded bg-primary-tint px-1.5 py-0.5 font-medium text-primary">
                              块 #{c.chunk_index}
                            </span>
                            {c.token_count != null && (
                              <span className="tabular-nums">
                                {c.token_count} 字
                              </span>
                            )}
                          </div>
                          <p className="whitespace-pre-wrap text-body-sm leading-relaxed text-ink-secondary">
                            {c.content}
                          </p>
                        </li>
                      ))}
                    </ul>
                    <div className="shrink-0">
                      <InvoiceListPager
                        page={page}
                        pageSize={pageSize}
                        total={chunks.length}
                        onPageChange={setPage}
                        onPageSizeChange={setPageSize}
                      />
                    </div>
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 右侧元数据面板：与中间卡片等高 */}
        <aside className="flex w-[280px] shrink-0 flex-col overflow-hidden lg:w-[300px]">
          <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="shrink-0 border-b border-line-subtle px-4 py-3">
              <h2 className="text-body-sm font-semibold text-ink">元数据</h2>
            </div>
            <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {!data && isFetching && (
                <p className="text-body-sm text-ink-tertiary">加载中…</p>
              )}
              {data && (
                <>
                  <MetaRow label="文档 ID" value={data.id} mono />
                  <MetaRow label="标题" value={data.title} />
                  <MetaRow
                    label="类型"
                    value={kbDocTypeLabel(data.doc_type)}
                  />
                  <MetaRow
                    label="状态"
                    value={
                      <Badge
                        tone={KB_STATUS_TONE[data.status] || 'neutral'}
                        dot
                      >
                        {KB_STATUS_LABEL[data.status] || data.status}
                      </Badge>
                    }
                  />
                  <MetaRow
                    label="切分块数"
                    value={
                      <span className="tabular-nums">{data.chunk_count}</span>
                    }
                  />
                  <MetaRow
                    label="版本"
                    value={<span className="tabular-nums">v{data.version}</span>}
                  />
                  <MetaRow
                    label="源文件"
                    value={data.source_file || '—'}
                  />
                  <MetaRow
                    label="Embedding"
                    value={data.embedding_model || '—'}
                  />
                  <MetaRow
                    label="创建时间"
                    value={formatDate(data.created_at)}
                  />
                  <MetaRow
                    label="更新时间"
                    value={formatDate(data.updated_at)}
                  />
                  {data.status === 'failed' && data.error_message && (
                    <div className="rounded-md border border-danger-border bg-danger-tint px-3 py-2">
                      <p className="text-label-sm font-medium text-danger">
                        错误信息
                      </p>
                      <p className="mt-1 text-body-sm text-danger">
                        {data.error_message}
                      </p>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  )
}

/** Tab 切换按钮。 */
function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative flex items-center gap-1.5 px-3 pb-3 text-body-sm font-medium transition-colors',
        active
          ? 'text-primary'
          : 'text-ink-tertiary hover:text-ink-secondary',
      )}
    >
      {icon}
      {label}
      {active && (
        <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary" />
      )}
    </button>
  )
}

/** 元数据行。 */
function MetaRow({
  label,
  value,
  mono,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div className="space-y-0.5">
      <dt className="text-label-sm text-ink-tertiary">{label}</dt>
      <dd
        className={cn(
          'break-all text-body-sm text-ink',
          mono && 'font-mono text-label-sm',
        )}
      >
        {value}
      </dd>
    </div>
  )
}
