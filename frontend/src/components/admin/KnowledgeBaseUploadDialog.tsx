import { useEffect, useState } from 'react'
import { Upload } from 'lucide-react'
import { toast } from 'sonner'

import { ChunkStrategySelector } from '@/components/admin/ChunkStrategySelector'
import { KB_DOC_TYPES } from '@/components/admin/kbMeta'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { KbChunkConfig, KbIndexSettings } from '@/types'

type UploadPayload = KbChunkConfig & {
  file: File
  title: string
  docType: string
  isGlobal: boolean
}

type KnowledgeBaseUploadDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  settings?: KbIndexSettings
  uploading: boolean
  onSubmit: (payload: UploadPayload) => Promise<void>
  onRetrieveTopKChange: (topK: number) => void
}

const DEFAULT_CHUNK_CONFIG: KbChunkConfig = {
  chunkStrategy: 'parent_child',
  chunkSize: 400,
  chunkOverlap: 50,
  parentSize: 1200,
  semanticThreshold: 0.45,
}

/** 上传文档弹窗：文件信息、切分配置和索引配置。 */
export function KnowledgeBaseUploadDialog({
  open,
  onOpenChange,
  settings,
  uploading,
  onSubmit,
  onRetrieveTopKChange,
}: KnowledgeBaseUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [docType, setDocType] = useState('policy')
  const [isGlobal, setIsGlobal] = useState(false)
  const [chunkConfig, setChunkConfig] =
    useState<KbChunkConfig>(DEFAULT_CHUNK_CONFIG)
  const [indexMode, setIndexMode] = useState('high_quality')
  const [retrieveTopK, setRetrieveTopK] = useState(5)

  useEffect(() => {
    if (!open || !settings) return
    setChunkConfig({
      chunkStrategy: settings.chunk_strategy || 'parent_child',
      chunkSize: settings.chunk_size,
      chunkOverlap: settings.chunk_overlap,
      parentSize: settings.parent_size || 1200,
      semanticThreshold: settings.semantic_threshold || 0.45,
    })
    setIndexMode(settings.index_mode)
    setRetrieveTopK(settings.retrieve_top_k)
  }, [open, settings])

  useEffect(() => {
    if (open) return
    setFile(null)
    setTitle('')
    setDocType('policy')
    setIsGlobal(false)
  }, [open])

  const accept = (
    settings?.allowed_suffixes || ['.txt', '.md', '.pdf', '.docx', '.doc']
  )
    .map((suffix) => (suffix.startsWith('.') ? suffix : `.${suffix}`))
    .join(',')

  /** 校验配置并提交上传。 */
  const handleConfirm = async () => {
    if (!file) {
      toast.error('请先选择文件')
      return
    }
    if (chunkConfig.chunkOverlap >= chunkConfig.chunkSize) {
      toast.error('重叠长度须小于分段长度')
      return
    }
    if (
      chunkConfig.chunkStrategy === 'parent_child' &&
      chunkConfig.parentSize <= chunkConfig.chunkSize
    ) {
      toast.error('父块长度须大于子块长度')
      return
    }
    onRetrieveTopKChange(retrieveTopK)
    await onSubmit({
      file,
      title,
      docType,
      isGlobal,
      ...chunkConfig,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[min(96vw,72rem)] max-w-5xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>上传知识库文档</DialogTitle>
          <DialogDescription>
            配置分段与索引参数后上传；系统将同步切分并写入混合索引。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">
              上传文本文件
            </h3>
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line-strong bg-canvas px-4 py-6 transition-colors hover:border-primary/40 hover:bg-primary-tint/30">
              <Upload className="h-5 w-5 text-primary" />
              <span className="text-body-sm text-ink">
                {file ? file.name : '点击选择或拖入文件'}
              </span>
              <span className="text-label-sm text-ink-tertiary">
                支持 txt / md / pdf / doc / docx，最大{' '}
                {Math.round(
                  (settings?.max_upload_bytes || 8 * 1024 * 1024) /
                    1024 /
                    1024,
                )}
                MB
              </span>
              <input
                type="file"
                accept={accept}
                className="hidden"
                onChange={(event) => {
                  const next = event.target.files?.[0] || null
                  setFile(next)
                  if (next && !title.trim()) {
                    setTitle(next.name.replace(/\.[^.]+$/, ''))
                  }
                  event.target.value = ''
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
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>文档类型</Label>
                <Select value={docType} onValueChange={setDocType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KB_DOC_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <label className="flex items-center gap-2 text-body-sm text-ink-secondary">
              <Checkbox
                checked={isGlobal}
                onCheckedChange={(value) => setIsGlobal(value === true)}
              />
              作为通用文档（全租户可见）
            </label>
          </section>

          <ChunkStrategySelector
            value={chunkConfig}
            settings={settings}
            onChange={setChunkConfig}
          />

          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">索引方式</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {(settings?.index_modes || []).map((mode) => {
                const selected = indexMode === mode.value
                return (
                  <button
                    key={mode.value}
                    type="button"
                    disabled={mode.disabled}
                    onClick={() => {
                      if (!mode.disabled) setIndexMode(mode.value)
                    }}
                    className={[
                      'rounded-lg border px-3 py-3 text-left transition-colors',
                      selected
                        ? 'border-primary bg-primary-tint/40'
                        : 'border-line-subtle bg-canvas',
                      mode.disabled
                        ? 'cursor-not-allowed opacity-50'
                        : 'hover:border-primary/40',
                    ].join(' ')}
                  >
                    <p className="text-body-sm font-medium text-ink">
                      {mode.label}
                    </p>
                    <p className="mt-1 text-label-sm text-ink-tertiary">
                      {mode.description}
                    </p>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">
              Embedding 模型
            </h3>
            <div className="rounded-lg border border-line-subtle bg-canvas px-3 py-3">
              <p className="text-body-sm font-medium text-ink">
                {settings?.embedding_model || '加载中…'}
              </p>
              <p className="mt-1 text-label-sm text-ink-tertiary">
                维数 {settings?.embedding_dimension ?? '—'}
                {settings?.milvus_enabled
                  ? ' · 写入 Milvus'
                  : ' · Milvus 未启用'}
              </p>
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-body-sm font-semibold text-ink">检索设置</h3>
            <div className="max-w-xs space-y-1.5">
              <Label htmlFor="kb-top-k">测试检索 Top-K</Label>
              <Input
                id="kb-top-k"
                type="number"
                min={1}
                max={20}
                value={retrieveTopK}
                onChange={(event) =>
                  setRetrieveTopK(Number(event.target.value) || 5)
                }
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
