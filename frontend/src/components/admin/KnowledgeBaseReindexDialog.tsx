import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { ChunkStrategySelector } from '@/components/admin/ChunkStrategySelector'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { KbChunkConfig, KbDocument, KbIndexSettings } from '@/types'

type KnowledgeBaseReindexDialogProps = {
  document: KbDocument | null
  settings?: KbIndexSettings
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (documentId: string, config: KbChunkConfig) => Promise<void>
}

/** 重新索引弹窗：允许真正切换策略和全部切分参数。 */
export function KnowledgeBaseReindexDialog({
  document,
  settings,
  submitting,
  onOpenChange,
  onSubmit,
}: KnowledgeBaseReindexDialogProps) {
  const [config, setConfig] = useState<KbChunkConfig>({
    chunkStrategy: 'parent_child',
    chunkSize: 400,
    chunkOverlap: 50,
    parentSize: 1200,
    semanticThreshold: 0.45,
  })

  useEffect(() => {
    if (!document) return
    const params = document.chunk_params
    setConfig({
      chunkStrategy:
        document.chunk_strategy ||
        settings?.chunk_strategy ||
        'parent_child',
      chunkSize:
        params?.child_size || settings?.chunk_size || 400,
      chunkOverlap:
        params?.overlap ?? settings?.chunk_overlap ?? 50,
      parentSize:
        params?.parent_size || settings?.parent_size || 1200,
      semanticThreshold:
        params?.semantic_threshold ||
        settings?.semantic_threshold ||
        0.45,
    })
  }, [document, settings])

  /** 校验后用选中的新策略覆盖文档原配置。 */
  const handleSubmit = async () => {
    if (!document) return
    if (config.chunkOverlap >= config.chunkSize) {
      toast.error('重叠长度须小于分段长度')
      return
    }
    if (
      config.chunkStrategy === 'parent_child' &&
      config.parentSize <= config.chunkSize
    ) {
      toast.error('父块长度须大于子块长度')
      return
    }
    await onSubmit(document.id, config)
  }

  return (
    <Dialog
      open={Boolean(document)}
      onOpenChange={(open) => onOpenChange(open)}
    >
      <DialogContent className="max-h-[90vh] w-[min(96vw,64rem)] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>重新切分并索引</DialogTitle>
          <DialogDescription>
            {document
              ? `将删除「${document.title}」的旧切块与向量，并按新配置重建。`
              : ''}
          </DialogDescription>
        </DialogHeader>

        <ChunkStrategySelector
          value={config}
          settings={settings}
          onChange={setConfig}
        />

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            type="button"
            disabled={submitting || !document}
            onClick={() => void handleSubmit()}
          >
            {submitting ? '重新索引中...' : '确认重新索引'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
