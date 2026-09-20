import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  FileText,
  RefreshCcw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader, StatCard } from '@/components/ui/stat'
import { EmptyState } from '@/components/ui/table'
import { kbApi } from '@/api/admin'
import { formatDate } from '@/lib/utils'

const STATUS_TONE: Record<string, 'success' | 'warning' | 'danger'> = {
  ready: 'success',
  indexing: 'warning',
  failed: 'danger',
}

const STATUS_LABEL: Record<string, string> = {
  ready: '已就绪',
  indexing: '索引中',
  failed: '失败',
}

export function KnowledgeBase() {
  const { data: docs, refetch } = useQuery({
    queryKey: ['kb-documents'],
    queryFn: () => kbApi.list(),
  })
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await kbApi.upload(formData)
      await refetch()
    } finally {
      setUploading(false)
    }
  }

  const totalChunks = (docs || []).reduce((sum, d) => sum + d.chunk_count, 0)
  const filtered = (docs || []).filter((d) =>
    d.title.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="RAG"
        title="知识库"
        description="上传制度文档以增强制度问答与合同审查能力"
        actions={
          <label>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt,.md"
              className="hidden"
              onChange={handleUpload}
            />
            <Button size="md" asChild>
              <span>
                <Upload className="h-4 w-4" />
                {uploading ? '上传中...' : '上传文档'}
              </span>
            </Button>
          </label>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="文档总数" value={docs?.length ?? 0} suffix="份" />
        <StatCard label="向量块数" value={totalChunks.toLocaleString()} />
        <StatCard label="本月检索" value="5,128" tone="success" delta={18.4} deltaLabel="较上月" />
      </div>

      <Card>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-line-subtle bg-surface">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary" />
            <Input
              placeholder="搜索文档标题"
              className="h-9 pl-8"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <span className="ml-auto text-body-sm text-ink-tertiary">
            共 {filtered.length} 份文档
          </span>
        </div>

        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <EmptyState
              icon={<BookOpen className="h-5 w-5" />}
              title="知识库为空"
              description="上传制度文档开始构建 RAG 检索能力"
            />
          ) : (
            <ul className="divide-y divide-line-subtle">
              {filtered.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center justify-between gap-4 px-5 py-4 hover:bg-canvas transition-colors"
                >
                  <div className="flex items-start gap-3 min-w-0 flex-1">
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
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      className="flex h-8 w-8 items-center justify-center rounded text-ink-tertiary hover:bg-surface-inset hover:text-ink"
                      aria-label="重新索引"
                    >
                      <RefreshCcw className="h-4 w-4" />
                    </button>
                    <button
                      className="flex h-8 w-8 items-center justify-center rounded text-ink-tertiary hover:bg-danger-tint hover:text-danger"
                      aria-label="删除文档"
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