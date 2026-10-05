import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

import { kbApi } from '@/api/admin'
import {
  KB_STATUS_LABEL,
  KB_STATUS_TONE,
  kbDocTypeLabel,
} from '@/components/admin/kbMeta'
import { KnowledgeBaseReindexDialog } from '@/components/admin/KnowledgeBaseReindexDialog'
import { KnowledgeBaseUploadDialog } from '@/components/admin/KnowledgeBaseUploadDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { SectionHeader, StatCard } from '@/components/ui/stat'
import { EmptyState } from '@/components/ui/table'
import { formatDate } from '@/lib/utils'
import type { KbChunkConfig, KbDocument } from '@/types'

type RetrieveHit = {
  chunk_id: string
  doc_id: string
  title?: string
  doc_type?: string
  content: string
  score: number
  source?: string
  reranked?: boolean
}

type UploadPayload = KbChunkConfig & {
  file: File
  title: string
  docType: string
  isGlobal: boolean
}

/** 管理端知识库：上传、策略化重索引、删除和检索测试。 */
export function KnowledgeBase() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: docs, refetch, isFetching } = useQuery({
    queryKey: ['kb-documents'],
    queryFn: () => kbApi.list(),
  })
  const { data: settings } = useQuery({
    queryKey: ['kb-settings'],
    queryFn: () => kbApi.settings(),
  })

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')
  const [question, setQuestion] = useState('合同合规审查要注意哪些条款？')
  const [topK, setTopK] = useState(5)
  const [hits, setHits] = useState<RetrieveHit[] | null>(null)
  const [retrieving, setRetrieving] = useState(false)
  const [reindexDocument, setReindexDocument] =
    useState<KbDocument | null>(null)

  useEffect(() => {
    if (settings?.retrieve_top_k) setTopK(settings.retrieve_top_k)
  }, [settings?.retrieve_top_k])

  const reindexMutation = useMutation({
    mutationFn: ({
      documentId,
      config,
    }: {
      documentId: string
      config: KbChunkConfig
    }) => kbApi.reindex(documentId, config),
    onSuccess: () => {
      toast.success('已按新策略重新切分并索引')
      setReindexDocument(null)
      queryClient.invalidateQueries({ queryKey: ['kb-documents'] })
    },
    onError: (error: unknown) => {
      toast.error(apiErrorMessage(error, '索引失败'))
      queryClient.invalidateQueries({ queryKey: ['kb-documents'] })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => kbApi.remove(id),
    onSuccess: () => {
      toast.success('已删除文档及全部索引')
      queryClient.invalidateQueries({ queryKey: ['kb-documents'] })
    },
    onError: () => toast.error('删除失败'),
  })

  /** 上传文件并把当前选择的切分策略传给后端。 */
  const handleUploadSubmit = async (payload: UploadPayload) => {
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', payload.file)
      if (payload.title.trim()) {
        formData.append('title', payload.title.trim())
      }
      formData.append('doc_type', payload.docType)
      formData.append('is_global', payload.isGlobal ? 'true' : 'false')
      formData.append('chunk_strategy', payload.chunkStrategy)
      formData.append('chunk_size', String(payload.chunkSize))
      formData.append('chunk_overlap', String(payload.chunkOverlap))
      formData.append('parent_size', String(payload.parentSize))
      formData.append(
        'semantic_threshold',
        String(payload.semanticThreshold),
      )
      const document = await kbApi.upload(formData)
      if (document.status === 'failed') {
        toast.error(document.error_message || '索引失败')
      } else {
        toast.success('上传并索引完成')
      }
      setUploadOpen(false)
      await refetch()
    } catch (error: unknown) {
      toast.error(apiErrorMessage(error, '上传失败'))
    } finally {
      setUploading(false)
    }
  }

  /** 执行混合检索测试并显示真实召回片段。 */
  const handleTestRetrieve = async () => {
    const query = question.trim()
    if (!query) {
      toast.error('请输入测试问题')
      return
    }
    setRetrieving(true)
    try {
      const result = (await kbApi.testRetrieve(query, topK)) as {
        items?: RetrieveHit[]
      }
      setHits(result.items || [])
      if (!(result.items || []).length) {
        toast.info('未召回片段')
      }
    } catch (error: unknown) {
      toast.error(apiErrorMessage(error, '检索失败'))
    } finally {
      setRetrieving(false)
    }
  }

  const documents = docs || []
  const filtered = documents.filter((document) =>
    document.title.toLowerCase().includes(search.toLowerCase()),
  )
  const readyCount = documents.filter(
    (document) =>
      document.status === 'active' || document.status === 'ready',
  ).length
  const totalChunks = documents.reduce(
    (sum, document) => sum + document.chunk_count,
    0,
  )

  return (
    <div className="space-y-6">
      <SectionHeader
        actions={
          <Button type="button" size="md" onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" />
            上传文档
          </Button>
        }
      />

      <KnowledgeBaseUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        settings={settings}
        uploading={uploading}
        onSubmit={handleUploadSubmit}
        onRetrieveTopKChange={setTopK}
      />
      <KnowledgeBaseReindexDialog
        document={reindexDocument}
        settings={settings}
        submitting={reindexMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setReindexDocument(null)
        }}
        onSubmit={(documentId, config) =>
          reindexMutation.mutateAsync({ documentId, config })
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="文档总数" value={documents.length} suffix="份" />
        <StatCard label="已就绪" value={readyCount} suffix="份" />
        <StatCard label="检索块数" value={totalChunks.toLocaleString()} />
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b border-line-subtle bg-surface px-4 py-3 sm:flex-row sm:items-center">
          <div className="relative max-w-xl flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-tertiary" />
            <Input
              placeholder="输入问题测试检索召回"
              className="h-9 pl-8"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void handleTestRetrieve()
              }}
            />
          </div>
          <Input
            aria-label="检索数量"
            type="number"
            min={1}
            max={20}
            className="h-9 w-20"
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value) || 5)}
          />
          <Button
            type="button"
            size="md"
            variant="secondary"
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
              hits.map((hit) => (
                <div
                  key={hit.chunk_id}
                  className="rounded-md border border-line-subtle bg-canvas px-3 py-2"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-label-sm text-ink-tertiary">
                    <span className="font-medium text-ink">
                      {hit.title || '未命名'}
                    </span>
                    <span>{hit.source || 'retrieve'}</span>
                    <span className="tabular-nums">
                      score {hit.score.toFixed(3)}
                    </span>
                    {hit.reranked && <span>rerank</span>}
                  </div>
                  <p className="whitespace-pre-wrap text-body-sm text-ink-secondary">
                    {hit.content}
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
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
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
              description="上传文档并选择切分策略"
            />
          ) : (
            <DocumentList
              documents={filtered}
              reindexing={reindexMutation.isPending}
              deleting={removeMutation.isPending}
              onOpen={(id) => navigate(`/admin/kb/${id}`)}
              onReindex={setReindexDocument}
              onDelete={(document) => {
                if (
                  window.confirm(
                    `确定删除「${document.title}」及全部索引？`,
                  )
                ) {
                  removeMutation.mutate(document.id)
                }
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

type DocumentListProps = {
  documents: KbDocument[]
  reindexing: boolean
  deleting: boolean
  onOpen: (id: string) => void
  onReindex: (document: KbDocument) => void
  onDelete: (document: KbDocument) => void
}

/** 文档列表及单文档操作。 */
function DocumentList({
  documents,
  reindexing,
  deleting,
  onOpen,
  onReindex,
  onDelete,
}: DocumentListProps) {
  return (
    <ul className="divide-y divide-line-subtle">
      {documents.map((document) => (
        <li
          key={document.id}
          className="flex cursor-pointer items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-canvas"
          onClick={() => onOpen(document.id)}
        >
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-tint text-primary">
              <FileText className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate text-body-md font-semibold text-ink">
                  {document.title}
                </span>
                <Badge tone={KB_STATUS_TONE[document.status] || 'neutral'} dot>
                  {KB_STATUS_LABEL[document.status] || document.status}
                </Badge>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 text-label-sm text-ink-tertiary">
                <span>{kbDocTypeLabel(document.doc_type)}</span>
                <span>{document.chunk_count} 个检索块</span>
                <span>v{document.version}</span>
                <span>{formatDate(document.created_at)}</span>
              </div>
              {document.status === 'failed' && document.error_message && (
                <p className="mt-1 text-label-sm text-danger">
                  {document.error_message}
                </p>
              )}
            </div>
          </div>

          <div
            className="flex shrink-0 items-center gap-1"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded text-ink-tertiary hover:bg-surface-inset hover:text-ink"
              aria-label="重新索引"
              title="重新索引"
              disabled={reindexing}
              onClick={() => onReindex(document)}
            >
              <RefreshCcw className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded text-ink-tertiary hover:bg-danger-tint hover:text-danger"
              aria-label="删除文档"
              title="删除"
              disabled={deleting}
              onClick={() => onDelete(document)}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </li>
      ))}
    </ul>
  )
}

/** 从 API 错误中提取业务文案。 */
function apiErrorMessage(error: unknown, fallback: string): string {
  return (
    (error as { response?: { data?: { message?: string } } })?.response?.data
      ?.message || fallback
  )
}
