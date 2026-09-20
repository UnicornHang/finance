import { cn } from '@/lib/utils'

/**
 * 品牌 Logo - 几何化 ¥ 符号
 * 单色版本适配深色/浅色背景
 */
export function BrandLogo({
  size = 32,
  className,
  withWordmark = false,
  tone = 'primary',
}: {
  size?: number
  className?: string
  withWordmark?: boolean
  tone?: 'primary' | 'white' | 'ink'
}) {
  const bg =
    tone === 'white'
      ? 'bg-surface-inset text-ink'
      : tone === 'ink'
        ? 'bg-ink text-white'
        : 'bg-primary text-white'

  return (
    <div className={cn('inline-flex items-center gap-2.5', className)}>
      <div
        className={cn(
          'inline-flex items-center justify-center rounded-md font-bold',
          bg,
        )}
        style={{ width: size, height: size, fontSize: size * 0.55 }}
      >
        ¥
      </div>
      {withWordmark && (
        <div className="flex flex-col leading-tight">
          <span className="text-title-lg font-semibold text-ink">Finance AI</span>
          <span className="text-label-sm uppercase tracking-wider text-ink-tertiary">
            Pristine Treasury
          </span>
        </div>
      )}
    </div>
  )
}

/**
 * 全宽页脚分隔
 */
export function Divider({
  orientation = 'horizontal',
  className,
}: {
  orientation?: 'horizontal' | 'vertical'
  className?: string
}) {
  return (
    <div
      className={cn(
        'bg-line-subtle',
        orientation === 'horizontal' ? 'h-px w-full' : 'w-px h-full',
        className,
      )}
      aria-hidden
    />
  )
}