import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen,
  FileText,
  RefreshCcw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader, StatCard } from '@/components/ui/stat'
import { EmptyState } from '@/components/ui/table'
import { kbApi } from '@/api/admin'
import { formatDate } from '@/lib/utils'

const STATUS_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  active: 'success',
  ready: 'success',
  indexing: 'warning',
  pending: 'neutral',
  failed: 'danger',
}

const STATUS_LABEL: Record<string, string> = {
  active: '已就绪',
  ready: '已就绪',
  indexing: '索引中',
  pending: '待索引',
  failed: '失败',
}

type RetrieveHit = {
  chunk_id: string
  doc_id: string
  title?: string
  doc_type?: string
  content: string
  score: number
  source?: string
}

/** 管理端知识库：上传/列表/重索引/删除/检索测试。 */
export function KnowledgeBase() {
  const queryClient = useQueryClient()
  const { data: docs, refetch, isFetching } = useQuery({
    queryKey: ['kb-documents'],
    queryFn: () => kbApi.list(),
  })
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')
  const [question, setQuestion] = useState('合同合规审查要注意哪些条款？')
  const [hits, setHits] = useState<RetrieveHit[] | null>(null)
  const [retrieving, setRetrieving] = useState(false)

  const reindexMutation = useMutation({
    mutationFn: (id: string) => kbApi.reindex(id),
    onSuccess: () => {
      toast.success('已重新索引')
      queryClient.invalidateQueries({ queryKey: ['kb-documents'] })
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || '索引失败'
      toast.error(msg)
      queryClient.invalidateQueries({ queryKey: ['kb-documents'] })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => kbApi.remove(id),
    onSuccess: () => {
      toast.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['kb-documents'] })
    },
    onError: () => toast.error('删除失败'),
  })

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const doc = await kbApi.upload(formData)
      if (doc.status === 'failed') {
        toast.error(doc.error_message || '索引失败，可稍后重试「重新索引」')
      } else {
        toast.success('上传并索引完成')
      }
      await refetch()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || '上传失败'
      toast.error(msg)
    } finally {
      setUploading(false)
    }
  }

  const handleTestRetrieve = async () => {
    const q = question.trim()
    if (!q) {
      toast.error('请输入测试问题')
      return
    }
    setRetrieving(true)
    try {
      const res = (await kbApi.testRetrieve(q)) as {
        items?: RetrieveHit[]
        total?: number
      }
      setHits(res.items || [])
      if (!(res.items || []).length) {
        toast.info('未召回片段，请先对文档执行「重新索引」')
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || '检索失败'
      toast.error(msg)
    } finally {
      setRetrieving(false)
    }
  }

  const totalChunks = (docs || []).reduce((sum, d) => sum + d.chunk_count, 0)
  const readyCount = (docs || []).filter(
    (d) => d.status === 'active' || d.status === 'ready',
  ).length
  const filtered = (docs || []).filter((d) =>
    d.title.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="space-y-6">
      <SectionHeader
        actions={
          <label>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt,.md,.markdown"
              className="hidden"
              onChange={(e) => void handleUpload(e)}
            />
            <Button size="md" asChild disabled={uploading}>
              <span>
                <Upload className="h-4 w-4" />
                {uploading ? '上传索引中...' : '上传文档'}
              </span>
            </Button>
          </label>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="文档总数" value={docs?.length ?? 0} suffix="份" />
        <StatCard label="已就绪" value={readyCount} suffix="份" />
        <StatCard label="向量块数" value={totalChunks.toLocaleString()} />
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b border-line-subtle bg-surface px-4 py-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 max-w-xl">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-tertiary" />
            <Input
              placeholder="输入问题测试检索召回"
              className="h-9 pl-8"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleTestRetrieve()
              }}
            />
          </div>
          <Button
            size="md"
            variant="secondary"
            type="button"
            disabled={retrieving}
            onClick={() => void handleTestRetrieve()}
          >
            <Search className="h-4 w-4" />
            {retrieving ? '检索中...' : '检索测试'}
          </Button>
        </div>
        {hits && (
          <CardContent className="space-y-3 p-4">
            {hits.length === 0 ? (
              <p className="text-body-sm text-ink-tertiary">无召回结果</p>
            ) : (
              hits.map((h) => (
                <div
                  key={h.chunk_id}
                  className="rounded-md border border-line-subtle bg-canvas px-3 py-2"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-label-sm text-ink-tertiary">
                    <span className="font-medium text-ink">{h.title || '未命名'}</span>
                    <span>·</span>
                    <span>{h.doc_type || '通用'}</span>
                    <span>·</span>
                    <span className="tabular-nums">score {h.score.toFixed(3)}</span>
                    {h.source && (
                      <>
                        <span>·</span>
                        <span>{h.source}</span>
                      </>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap text-body-sm text-ink-secondary">
                    {h.content}
                  </p>
                </div>
              ))
            )}
          </CardContent>
        )}
      </Card>

      <Card>
        <div className="flex items-center gap-2 border-b border-line-subtle bg-surface px-4 py-3">
          <div className="relative max-w-md flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-tertiary" />
            <Input
              placeholder="搜索文档标题"
              className="h-9 pl-8"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Button
            size="sm"
            variant="ghost"
            type="button"
            disabled={isFetching}
            onClick={() => void refetch()}
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            刷新
          </Button>
          <span className="ml-auto text-body-sm text-ink-tertiary">
            共 {filtered.length} 份文档
          </span>
        </div>

        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <EmptyState
              icon={<BookOpen className="h-5 w-5" />}
              title="知识库为空"
              description="上传制度文档，或对种子文档点击「重新索引」完成向量化"
            />
          ) : (
            <ul className="divide-y divide-line-subtle">
              {filtered.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-canvas"
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-tint text-primary">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-body-md font-semibold text-ink">
                          {d.title}
                        </p>
                        <Badge tone={STATUS_TONE[d.status] || 'neutral'} dot>
                          {STATUS_LABEL[d.status] || d.status}
                        </Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-label-sm text-ink-tertiary">
                        <span>{d.doc_type || '通用'}</span>
                        <span className="text-line">·</span>
                        <span className="tabular-nums">{d.chunk_count} 块</span>
                        <span className="text-line">·</span>
                        <span>v{d.version}</span>
                        <span className="text-line">·</span>
                        <span>{formatDate(d.created_at)}</span>
                      </div>
                      {d.status === 'failed' && d.error_message && (
                        <p className="mt-1 text-label-sm text-danger">{d.error_message}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      className="flex h-8 w-8 items-center justify-center rounded text-ink-tertiary hover:bg-surface-inset hover:text-ink"
                      aria-label="重新索引"
                      title="重新索引"
                      disabled={reindexMutation.isPending}
                      onClick={() => reindexMutation.mutate(d.id)}
                    >
                      <RefreshCcw className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      className="flex h-8 w-8 items-center justify-center rounded text-ink-tertiary hover:bg-danger-tint hover:text-danger"
                      aria-label="删除文档"
                      title="删除"
                      disabled={removeMutation.isPending}
                      onClick={() => {
                        if (window.confirm(`确定删除「${d.title}」？`)) {
                          removeMutation.mutate(d.id)
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
