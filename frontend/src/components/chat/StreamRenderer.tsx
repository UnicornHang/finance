import { useUIStore } from '@/stores/uiStore'

/**
 * 流式思考状态指示器
 * - 固定位置于 chat header 下方
 * - 跳动蓝点 + 文字
 */
export function StreamRenderer() {
  const streaming = useUIStore((s) => s.streaming)

  if (!streaming) return null

  return (
    <div className="flex items-center gap-2 px-6 py-2 text-body-sm text-ink-tertiary">
      <span className="relative flex h-2 w-2">
        <span className="absolute inset-0 animate-pulse-soft rounded-full bg-primary/40" />
        <span className="relative inline-block h-2 w-2 rounded-full bg-primary" />
      </span>
      <span>AI 正在思考</span>
    </div>
  )
}