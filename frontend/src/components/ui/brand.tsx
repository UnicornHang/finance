import { cn } from '@/lib/utils'
import logoImg from '@/assets/image/logo.png'

/**
 * 品牌 Logo - 使用官方 logo 图片
 * tone 保留以兼容调用方，图片本身已带品牌色
 */
export function BrandLogo({
  size = 32,
  className,
  withWordmark = false,
  tone: _tone = 'primary',
}: {
  size?: number
  className?: string
  withWordmark?: boolean
  tone?: 'primary' | 'white' | 'ink'
}) {
  return (
    <div className={cn('inline-flex items-center gap-2.5', className)}>
      <img
        src={logoImg}
        alt="Finance AI"
        width={size}
        height={size}
        className="rounded-md object-contain"
        style={{ width: size, height: size }}
      />
      {withWordmark && (
        <span className="bg-gradient-to-r from-[#006194] via-[#0284c7] to-[#0ea5e9] bg-clip-text text-title-lg font-semibold leading-none text-transparent">
          Finance AI
        </span>
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