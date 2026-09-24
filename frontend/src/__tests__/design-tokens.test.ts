import { describe, it, expect } from 'vitest'
import tailwindConfig from '../../tailwind.config'

/**
 * 设计 Token 锁版测试
 *
 * 目的：保证"现代 AI Agent"风格的圆角、字体、阴影等核心 Token
 * 在后续提交中不会被无意改回"硬核金融科技"风格。
 *
 * 一旦以下数值被修改，必须经过 UI/UX 评审。
 */
describe('设计 Token —— 现代 AI Agent 风格锁版', () => {
  const theme = tailwindConfig.theme.extend as Record<string, any>

  describe('fontFamily', () => {
    it('sans 应以 Inter 为主字体 (现代 AI 产品主流)', () => {
      expect(theme.fontFamily.sans[0]).toBe('Inter')
    })

    it('mono 应提供 JetBrains Mono (财务数字 / 代码对齐)', () => {
      expect(theme.fontFamily.mono[0]).toBe('"JetBrains Mono"')
    })
  })

  describe('borderRadius - 柔和圆角体系', () => {
    it('lg 应为 12px (卡片)', () => {
      expect(theme.borderRadius.lg).toBe('0.75rem')
    })

    it('xl 应为 16px (弹窗 / Sheet)', () => {
      expect(theme.borderRadius.xl).toBe('1rem')
    })

    it('2xl 应为 20px (大弹窗)', () => {
      expect(theme.borderRadius['2xl']).toBe('1.25rem')
    })

    it('保留 24px (3xl) 用于全屏弹层', () => {
      expect(theme.borderRadius['3xl']).toBe('1.5rem')
    })
  })

  describe('boxShadow - 软染色投影体系', () => {
    it('应保留 shadow-elevated 用于弹层', () => {
      expect(theme.boxShadow.elevated).toContain('rgba(15, 23, 42')
      expect(theme.boxShadow.elevated).not.toContain('rgb(203 213 225)')
    })

    it('应保留 shadow-soft 用于卡片', () => {
      expect(theme.boxShadow.soft).toBeDefined()
    })

    it('应保留 shadow-glow-primary 用于 AI 高亮', () => {
      expect(theme.boxShadow['glow-primary']).toContain('14, 165, 233')
    })

    it('hairline 仍存在以兼容 1px border 模拟', () => {
      expect(theme.boxShadow.hairline).toContain('230 233 240')
    })
  })

  describe('transitionTimingFunction - 平滑缓动', () => {
    it('应提供 smooth 缓动 (弹窗/抽屉)', () => {
      expect(theme.transitionTimingFunction.smooth).toBe(
        'cubic-bezier(0.32, 0.72, 0, 1)',
      )
    })

    it('应提供 snappy 缓动 (微交互)', () => {
      expect(theme.transitionTimingFunction.snappy).toBe(
        'cubic-bezier(0.22, 1, 0.36, 1)',
      )
    })
  })

  describe('animation - 现代入场动画', () => {
    it('fade-in 应使用 smooth 缓动', () => {
      expect(theme.animation['fade-in']).toContain('cubic-bezier(0.32, 0.72, 0, 1)')
    })

    it('slide-up 应使用 smooth 缓动', () => {
      expect(theme.animation['slide-up']).toContain('cubic-bezier(0.32, 0.72, 0, 1)')
    })

    it('scale-in 应使用 smooth 缓动', () => {
      expect(theme.animation['scale-in']).toContain('cubic-bezier(0.32, 0.72, 0, 1)')
    })
  })

  describe('colors - 现代配色', () => {
    it('primary 主色升级为 #0ea5e9 (Sky 500)', () => {
      expect(theme.colors.primary.DEFAULT).toBe('#0ea5e9')
    })

    it('canvas 背景使用 Soft Mist', () => {
      expect(theme.colors.canvas).toBe('#f7f8fb')
    })

    it('line 边框采用更柔和的 #e6e9f0', () => {
      expect(theme.colors.line.DEFAULT).toBe('#e6e9f0')
    })
  })
})
