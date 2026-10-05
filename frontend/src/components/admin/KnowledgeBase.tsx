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

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { SectionHeader, StatCard } from '@/components/ui/stat'
import { EmptyState } from '@/components/ui/table'
import {
  KB_DOC_TYPES,
  KB_STATUS_LABEL,
  KB_STATUS_TONE,
  kbDocTypeLabel,
} from '@/components/admin/kbMeta'
import { kbApi } from '@/api/admin'
import { formatDate } from '@/lib/utils'
import type { KbIndexSettings } from '@/types'

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

/** 管理端知识库：上传弹窗 / 列表 / 重索引 / 删除 / 检索测试。 */
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

  useEffect(() => {
    if (settings?.retrieve_top_k) setTopK(settings.retrieve_top_k)
  }, [settings?.retrieve_top_k])

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

  const handleUploadSubmit = async (payload: {
    file: File
    title: string
    docType: string
    isGlobal: boolean
    chunkSize: number
    chunkOverlap: number
  }) => {
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', payload.file)
      if (payload.title.trim()) formData.append('title', payload.title.trim())
      formData.append('doc_type', payload.docType)
      formData.append('is_global', payload.isGlobal ? 'true' : 'false')
      formData.append('chunk_size', String(payload.chunkSize))
      formData.append('chunk_overlap', String(payload.chunkOverlap))
      const doc = await kbApi.upload(formData)
      if (doc.status === 'failed') {
        toast.error(doc.error_message || '索引失败，可稍后重试「重新索引」')
      } else {
        toast.success('上传并索引完成')
      }
      setUploadOpen(false)
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
      const res = (await kbApi.testRetrieve(q, topK)) as {
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
          <Button size="md" type="button" onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" />
            上传文档
          </Button>
        }
      />

      <KbUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        settings={settings}
        uploading={uploading}
        onSubmit={handleUploadSubmit}
        onRetrieveTopKChange={setTopK}
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
          <div className="flex items-center gap-2">
            <Label className="whitespace-nowrap text-label-sm text-ink-tertiary">
              Top-K
            </Label>
            <Input
              type="number"
              min={1}
              max={20}
              className="h-9 w-16"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value) || 5)}
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
                    {h.reranked && (
                      <>
                        <span>·</span>
                        <span>rerank</span>
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
                  role="button"
                  tabIndex={0}
                  className="flex cursor-pointer items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-canvas"
                  onClick={() => navigate(`/admin/kb/${d.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      navigate(`/admin/kb/${d.id}`)
                    }
                  }}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-tint text-primary">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-body-md font-semibold text-ink">
                          {d.title}
                        </span>
                        <Badge tone={KB_STATUS_TONE[d.status] || 'neutral'} dot>
                          {KB_STATUS_LABEL[d.status] || d.status}
                        </Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-label-sm text-ink-tertiary">
                        <span>{kbDocTypeLabel(d.doc_type)}</span>
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

                  <div
                    className="flex shrink-0 items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
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

type UploadFormProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  settings?: KbIndexSettings
  uploading: boolean
  onSubmit: (payload: {
    file: File
    title: string
    docType: string
    isGlobal: boolean
    chunkSize: number
    chunkOverlap: number
  }) => Promise<void>
  onRetrieveTopKChange: (k: number) => void
}

/** 上传文档弹窗：分段 / 索引方式 / Embedding / 检索 / 选文件。 */
function KbUploadDialog({
  open,
  onOpenChange,
  settings,
  uploading,
  onSubmit,
  onRetrieveTopKChange,
}: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('policy')
  const [isGlobal, setIsGlobal] = useState(false)
  const [chunkSize, setChunkSize] = useState(500)
  const [chunkOverlap, setChunkOverlap] = useState(50)
  const [indexMode, setIndexMode] = useState('high_quality')
  const [retrieveTopK, setRetrieveTopK] = useState(5)

  useEffect(() => {
    if (!open || !settings) return
    setChunkSize(settings.chunk_size)
    setChunkOverlap(settings.chunk_overlap)
    setIndexMode(settings.index_mode)
    setRetrieveTopK(settings.retrieve_top_k)
  }, [open, settings])

  useEffect(() => {
    if (!open) {
      setFile(null)
      setTitle('')
      setDocType('policy')
      setIsGlobal(false)
    }
  }, [open])

  const accept = (settings?.allowed_suffixes || ['.txt', '.md', '.pdf', '.docx', '.doc'])
    .map((s) => (s.startsWith('.') ? s : `.${s}`))
    .join(',')

  const handleConfirm = async () => {
    if (!file) {
      toast.error('请先选择文件')
      return
    }
    if (chunkOverlap >= chunkSize) {
      toast.error('重叠长度须小于分段长度')
      return
    }
    onRetrieveTopKChange(retrieveTopK)
    await onSubmit({
      file,
      title,
      docType,
      isGlobal,
      chunkSize,
      chunkOverlap,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>上传知识库文档</DialogTitle>
          <DialogDescription>
            配置分段与索引参数后上传；系统将切分并写入向量库。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          {/* 上传文本文件 */}
          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">上传文本文件</h3>
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line-strong bg-canvas px-4 py-6 transition-colors hover:border-primary/40 hover:bg-primary-tint/30">
              <Upload className="h-5 w-5 text-primary" />
              <span className="text-body-sm text-ink">
                {file ? file.name : '点击选择或拖入文件'}
              </span>
              <span className="text-label-sm text-ink-tertiary">
                支持 txt / md / pdf / doc / docx，最大{' '}
                {Math.round((settings?.max_upload_bytes || 8 * 1024 * 1024) / 1024 / 1024)}MB
              </span>
              <input
                type="file"
                accept={accept}
                className="hidden"
                onChange={(e) => {
                  const next = e.target.files?.[0] || null
                  setFile(next)
                  if (next && !title.trim()) {
                    setTitle(next.name.replace(/\.[^.]+$/, ''))
                  }
                  e.target.value = ''
                }}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="kb-title">文档标题</Label>
                <Input
                  id="kb-title"
                  placeholder="默认取文件名"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>文档类型</Label>
                <Select value={docType} onValueChange={setDocType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KB_DOC_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <label className="flex items-center gap-2 text-body-sm text-ink-secondary">
              <Checkbox
                checked={isGlobal}
                onCheckedChange={(v) => setIsGlobal(v === true)}
              />
              作为通用文档（全租户可见）
            </label>
          </section>

          {/* 分段设置 */}
          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">分段设置</h3>
            <p className="text-label-sm text-ink-tertiary">
              递归按段落切分；块过长时再按长度切分并保留重叠。
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="kb-chunk-size">分段最大长度</Label>
                <Input
                  id="kb-chunk-size"
                  type="number"
                  min={100}
                  max={4000}
                  value={chunkSize}
                  onChange={(e) => setChunkSize(Number(e.target.value) || 500)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="kb-chunk-overlap">分段重叠长度</Label>
                <Input
                  id="kb-chunk-overlap"
                  type="number"
                  min={0}
                  max={2000}
                  value={chunkOverlap}
                  onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
                />
              </div>
            </div>
          </section>

          {/* 索引方式 */}
          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">索引方式</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {(settings?.index_modes || [
                {
                  value: 'high_quality',
                  label: '高质量（向量）',
                  description: '切分后 Embedding，写入向量库',
                },
              ]).map((mode) => {
                const selected = indexMode === mode.value
                const disabled = Boolean(mode.disabled)
                return (
                  <button
                    key={mode.value}
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      if (!disabled) setIndexMode(mode.value)
                    }}
                    className={[
                      'rounded-lg border px-3 py-3 text-left transition-colors',
                      selected
                        ? 'border-primary bg-primary-tint/40'
                        : 'border-line-subtle bg-canvas',
                      disabled ? 'cursor-not-allowed opacity-50' : 'hover:border-primary/40',
                    ].join(' ')}
                  >
                    <p className="text-body-sm font-medium text-ink">{mode.label}</p>
                    <p className="mt-1 text-label-sm text-ink-tertiary">
                      {mode.description}
                    </p>
                  </button>
                )
              })}
            </div>
          </section>

          {/* Embedding 模型 */}
          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">Embedding 模型</h3>
            <div className="rounded-lg border border-line-subtle bg-canvas px-3 py-3">
              <p className="text-body-sm font-medium text-ink">
                {settings?.embedding_model || '加载中…'}
              </p>
              <p className="mt-1 text-label-sm text-ink-tertiary">
                维数 {settings?.embedding_dimension ?? '—'}
                {settings?.milvus_enabled ? ' · 写入 Milvus' : ' · Milvus 未启用'}
              </p>
              <p className="mt-1 truncate text-label-sm text-ink-tertiary">
                {settings?.embedding_base_url || ''}
              </p>
              <p className="mt-2 text-label-sm text-ink-tertiary">
                模型由服务端 `.env` 配置；更换后需对已有文档执行「重新索引」。
              </p>
            </div>
          </section>

          {/* 检索设置 */}
          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">检索设置</h3>
            <p className="text-label-sm text-ink-tertiary">
              影响本页「检索测试」默认召回条数；向量检索使用 COSINE。
            </p>
            <div className="max-w-xs space-y-1.5">
              <Label htmlFor="kb-top-k">Top-K</Label>
              <Input
                id="kb-top-k"
                type="number"
                min={1}
                max={20}
                value={retrieveTopK}
                onChange={(e) => setRetrieveTopK(Number(e.target.value) || 5)}
              />
            </div>
          </section>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            disabled={uploading}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            type="button"
            disabled={uploading || !file}
            onClick={() => void handleConfirm()}
          >
            {uploading ? '上传索引中...' : '开始上传并索引'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
