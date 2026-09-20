import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Navigate } from 'react-router-dom'
import { ArrowRight, KeyRound, User2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/input'
import { BrandLogo } from '@/components/ui/brand'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { loginSchema, type LoginInput } from '@/lib/validators'

export function Login() {
  const isAuthed = useAuthStore((s) => !!s.token)
  const { login, isLoading } = useAuth()

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { account: '', password: '' },
  })

  if (isAuthed) return <Navigate to="/chat" replace />

  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)] bg-canvas">
      {/* 左侧品牌叙事区 — 仅 lg+ 显示 */}
      <aside className="relative hidden lg:flex flex-col justify-between p-12 bg-surface border-r border-line overflow-hidden">
        <BrandLogo size={36} withWordmark />

        <div className="space-y-8 max-w-md">
          <div className="space-y-3">
            <Badge tone="primary" dot>
              Pristine Crisp Fintech
            </Badge>
            <h1 className="text-display-lg font-bold tracking-tight text-ink">
              对话即操作<br />
              AI 主导财务工作流
            </h1>
            <p className="text-body-lg text-ink-secondary">
              发票识别、合同审查、制度问答——所有财务任务，
              <br />
              在同一个干净的对话入口完成。
            </p>
          </div>

          <ul className="space-y-3 text-body-md text-ink-secondary">
            <li className="flex items-start gap-3">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <span>上传即识别，AI 自动结构化字段，人工确认后归档</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <span>合同 RAG 规则匹配，风险等级自动标注</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <span>完整的多租户隔离与会话上下文管理</span>
            </li>
          </ul>
        </div>

        <footer className="flex items-center justify-between text-body-sm text-ink-tertiary">
          <span>私有化部署 · v1.0</span>
          <span>Made with Pristine Crisp Fintech</span>
        </footer>
      </aside>

      {/* 右侧登录表单 */}
      <main className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm space-y-8">
          <div className="lg:hidden">
            <BrandLogo size={36} withWordmark />
          </div>

          <header className="space-y-2">
            <h2 className="text-headline-lg font-semibold text-ink">登录</h2>
            <p className="text-body-md text-ink-tertiary">
              使用您的企业账号继续
            </p>
          </header>

          <form
            onSubmit={form.handleSubmit((data) => login(data))}
            className="space-y-5"
            noValidate
          >
            <div className="space-y-1.5">
              <Label htmlFor="account">账号</Label>
              <div className="relative">
                <User2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-tertiary pointer-events-none" />
                <Input
                  id="account"
                  placeholder="请输入账号"
                  className="pl-9"
                  autoComplete="username"
                  {...form.register('account')}
                  invalid={!!form.formState.errors.account}
                  disabled={isLoading}
                />
              </div>
              {form.formState.errors.account && (
                <p className="text-body-sm text-danger">
                  {form.formState.errors.account.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">密码</Label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-tertiary pointer-events-none" />
                <Input
                  id="password"
                  type="password"
                  placeholder="请输入密码"
                  className="pl-9"
                  autoComplete="current-password"
                  {...form.register('password')}
                  invalid={!!form.formState.errors.password}
                  disabled={isLoading}
                />
              </div>
              {form.formState.errors.password && (
                <p className="text-body-sm text-danger">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full text-white"
              disabled={isLoading}
            >
              {isLoading ? '登录中...' : '登录'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          <div className="rounded-lg border border-line-subtle bg-surface p-4 space-y-2">
            <p className="text-label-md font-semibold uppercase tracking-wider text-ink-tertiary">
              默认账号
            </p>
            <div className="grid grid-cols-3 gap-3 text-body-sm">
              <div>
                <p className="font-mono text-ink">admin</p>
                <p className="text-ink-tertiary">Admin@123</p>
              </div>
              <div>
                <p className="font-mono text-ink">finance01</p>
                <p className="text-ink-tertiary">Finance@123</p>
              </div>
              <div>
                <p className="font-mono text-ink">employee01</p>
                <p className="text-ink-tertiary">Emp@123</p>
              </div>
            </div>
          </div>

          <p className="text-center text-body-sm text-ink-tertiary">
            首次登录将强制修改密码
          </p>
        </div>
      </main>
    </div>
  )
}