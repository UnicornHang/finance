import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

/**
 * UI 原子组件 —— 现代 AI Agent 风格锁版测试
 *
 * 锁版关键 class：
 * - 弹窗: rounded-2xl + shadow-elevated + border-line/80
 * - 卡片: rounded-xl + shadow-soft + border-line/90
 * - 按钮: ease-smooth + focus-visible:ring-4
 * - 输入框: ease-smooth + focus-visible:ring-4
 */
describe('UI 原子组件 —— 现代 AI Agent 风格锁版', () => {
  describe('Dialog (居中弹窗)', () => {
    it('DialogContent 应使用 16px 圆角 (rounded-2xl)', () => {
      render(
        <Dialog defaultOpen>
          <DialogContent data-testid="dialog">
            <DialogHeader>
              <DialogTitle>测试标题</DialogTitle>
              <DialogDescription>测试描述</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button>确定</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>,
      )

      const dialog = screen.getByTestId('dialog')
      expect(dialog.className).toContain('rounded-2xl')
      expect(dialog.className).toContain('shadow-elevated')
      expect(dialog.className).toContain('border-line/80')
    })

    it('DialogContent 应使用 smooth 缓动', () => {
      render(
        <Dialog defaultOpen>
          <DialogContent data-testid="dialog">内容</DialogContent>
        </Dialog>,
      )
      const dialog = screen.getByTestId('dialog')
      expect(dialog.className).toContain('ease-smooth')
    })

    it('DialogContent 应有 slide-in-from-bottom 入场动画', () => {
      render(
        <Dialog defaultOpen>
          <DialogContent data-testid="dialog">内容</DialogContent>
        </Dialog>,
      )
      const dialog = screen.getByTestId('dialog')
      expect(dialog.className).toContain('slide-in-from-bottom-2')
    })
  })

  describe('Card (容器卡片)', () => {
    it('Card 应使用 12px 圆角 (rounded-xl)', () => {
      render(
        <Card data-testid="card">
          <CardHeader>
            <CardTitle>测试卡片</CardTitle>
          </CardHeader>
          <CardContent>内容</CardContent>
        </Card>,
      )
      const card = screen.getByTestId('card')
      expect(card.className).toContain('rounded-xl')
    })

    it('Card 应使用 shadow-soft 软投影', () => {
      render(<Card data-testid="card">内容</Card>)
      const card = screen.getByTestId('card')
      expect(card.className).toContain('shadow-soft')
    })

    it('Card 应使用更柔和的边框 (border-line/90)', () => {
      render(<Card data-testid="card">内容</Card>)
      const card = screen.getByTestId('card')
      expect(card.className).toContain('border-line/90')
    })
  })

  describe('Button (按钮)', () => {
    it('Button 应使用 ease-smooth 缓动', () => {
      render(<Button data-testid="btn">按钮</Button>)
      const btn = screen.getByTestId('btn')
      expect(btn.className).toContain('ease-smooth')
    })

    it('Button 应使用更柔和的 focus ring (focus-visible:ring-4 + primary/20)', () => {
      render(<Button data-testid="btn">按钮</Button>)
      const btn = screen.getByTestId('btn')
      expect(btn.className).toContain('focus-visible:ring-4')
      expect(btn.className).toContain('focus-visible:ring-primary/20')
    })
  })

  describe('Input (输入框)', () => {
    it('Input 应使用 ease-smooth 缓动', () => {
      render(<Input data-testid="input" placeholder="请输入" />)
      const input = screen.getByTestId('input')
      expect(input.className).toContain('ease-smooth')
    })

    it('Input 应使用更柔和的 focus ring (focus-visible:ring-4 + primary/15)', () => {
      render(<Input data-testid="input" placeholder="请输入" />)
      const input = screen.getByTestId('input')
      expect(input.className).toContain('focus-visible:ring-4')
      expect(input.className).toContain('focus-visible:ring-primary/15')
    })

    it('Input 失效态应使用 danger/20 软光晕', () => {
      render(<Input data-testid="input" invalid placeholder="请输入" />)
      const input = screen.getByTestId('input')
      expect(input.className).toContain('focus-visible:ring-danger/20')
    })
  })
})
