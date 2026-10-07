import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import {
  RefreshCw,
  RotateCcw,
  RotateCw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const MIN_SCALE = 0.25
const MAX_SCALE = 5
const SCALE_STEP = 0.15

interface Props {
  src: string
  alt: string
}

/** 将缩放比例夹在合理区间内 */
function clampScale(value: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))
}

/**
 * 图片预览交互区：滚轮缩放、左右旋转、拖拽平移，以及工具栏快捷操作。
 */
export function ImagePreviewViewer({ src, alt }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{
    startX: number
    startY: number
    originX: number
    originY: number
  } | null>(null)

  const [scale, setScale] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)

  /** 切换图片时重置变换状态 */
  useEffect(() => {
    setScale(1)
    setRotation(0)
    setOffset({ x: 0, y: 0 })
    setDragging(false)
    dragRef.current = null
  }, [src])

  /** 滚轮缩放：在视口上拦截默认滚动，按 delta 方向放大/缩小 */
  useEffect(() => {
    const el = viewportRef.current
    if (!el) return

    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const delta = event.deltaY > 0 ? -SCALE_STEP : SCALE_STEP
      setScale((prev) => clampScale(Number((prev + delta).toFixed(2))))
    }

    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  /** 放大一档 */
  const zoomIn = useCallback(() => {
    setScale((prev) => clampScale(Number((prev + SCALE_STEP).toFixed(2))))
  }, [])

  /** 缩小一档 */
  const zoomOut = useCallback(() => {
    setScale((prev) => clampScale(Number((prev - SCALE_STEP).toFixed(2))))
  }, [])

  /** 顺时针旋转 90° */
  const rotateCw = useCallback(() => {
    setRotation((prev) => (prev + 90) % 360)
  }, [])

  /** 逆时针旋转 90° */
  const rotateCcw = useCallback(() => {
    setRotation((prev) => (prev + 270) % 360)
  }, [])

  /** 恢复默认缩放、旋转与位移 */
  const resetView = useCallback(() => {
    setScale(1)
    setRotation(0)
    setOffset({ x: 0, y: 0 })
  }, [])

  /** 开始拖拽平移 */
  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      // 仅主键拖拽
      if (event.button !== 0) return
      event.currentTarget.setPointerCapture(event.pointerId)
      dragRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: offset.x,
        originY: offset.y,
      }
      setDragging(true)
    },
    [offset.x, offset.y],
  )

  /** 拖拽过程中更新位移 */
  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current
      if (!drag) return
      setOffset({
        x: drag.originX + (event.clientX - drag.startX),
        y: drag.originY + (event.clientY - drag.startY),
      })
    },
    [],
  )

  /** 结束拖拽 */
  const onPointerUp = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    dragRef.current = null
    setDragging(false)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }, [])

  const scalePercent = Math.round(scale * 100)

  return (
    <div className="flex w-full flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={zoomOut}
            disabled={scale <= MIN_SCALE}
            aria-label="缩小"
            title="缩小"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="min-w-[3.5rem] text-center text-label-sm tabular-nums text-ink-secondary">
            {scalePercent}%
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={zoomIn}
            disabled={scale >= MAX_SCALE}
            aria-label="放大"
            title="放大"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={rotateCcw}
            aria-label="逆时针旋转"
            title="逆时针旋转"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={rotateCw}
            aria-label="顺时针旋转"
            title="顺时针旋转"
          >
            <RotateCw className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={resetView}
            aria-label="重置视图"
            title="重置视图"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-label-sm text-ink-tertiary">滚轮缩放 · 拖拽平移</p>
      </div>

      <div
        ref={viewportRef}
        className={cn(
          'relative h-[min(80vh,calc(95vh-8rem))] w-full overflow-hidden rounded-md border border-line bg-canvas',
          dragging ? 'cursor-grabbing' : 'cursor-grab',
        )}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div
          className="flex h-full w-full items-center justify-center"
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px)`,
          }}
        >
          <img
            src={src}
            alt={alt}
            draggable={false}
            className="max-h-full max-w-full select-none object-contain"
            style={{
              transform: `scale(${scale}) rotate(${rotation}deg)`,
              transformOrigin: 'center center',
              transition: dragging ? 'none' : 'transform 120ms ease-out',
            }}
          />
        </div>
      </div>
    </div>
  )
}
