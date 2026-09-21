import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Navigate } from 'react-router-dom'
import { User2, Lock, Eye, EyeOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { loginSchema, type LoginInput } from '@/lib/validators'

import loginBg from '@/assets/image/login_bg.png'
import loginContent from '@/assets/image/login_content.jpg'
import logoPng from '@/assets/image/logo.png'

export function Login() {
  const isAuthed = useAuthStore((s) => !!s.token)
  const { login, isLoading } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { account: '', password: '' },
  })

  if (isAuthed) return <Navigate to="/chat" replace />

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden bg-cover bg-center bg-no-repeat"
      style={{ backgroundImage: `url(${loginBg})` }}
    >
      {/* 深蓝蒙版，提升前景可读性 */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#0a1f5c]/70 via-[#0c2a8a]/55 to-[#0a1f5c]/75" />

      <div className="relative z-10 grid min-h-screen grid-cols-1 lg:grid-cols-2">
        {/* ============ 左侧品牌叙事区 ============ */}
        <aside className="hidden lg:flex flex-col justify-between p-12 xl:p-16 text-white">
          {/* 顶部：logo + 品牌名 + 副标题 */}
          <header className="flex items-center justify-center gap-3">
            {/* <img
              src={logoPng}
              alt="企业 AI Agent 财务平台 logo"
              className="h-12 w-12 object-contain drop-shadow-[0_2px_8px_rgba(59,130,246,0.5)]"
            /> */}
            <div className="flex flex-col leading-tight text-center">
              {/* <h1 className="text-headline-md font-bold tracking-wide">
                企业AI Agent 财务平台
              </h1>
              <p className="text-label-sm uppercase tracking-[0.3em] text-blue-200/80">
                AI · FINANCE · FUTURE
              </p> */}
            </div>
          </header>

          {/* 中部：机器人 IP + 大标题 */}
          <div className="flex flex-col items-center gap-8 my-8">
            <img
              src={loginContent}
              alt="AI 财务机器人"
              className="w-[420px] xl:w-[480px] max-w-full drop-shadow-[0_20px_60px_rgba(56,189,248,0.45)]"
            />
            <div className="text-center space-y-4">
              <h2 className="text-display-lg font-bold leading-tight">
                用{' '}
                <span className="bg-gradient-to-r from-cyan-300 via-sky-300 to-blue-300 bg-clip-text text-transparent">
                  AI
                </span>{' '}
                让财务更智能
              </h2>
              <p className="text-body-lg text-blue-100/85 tracking-widest">
                智能分析 · 高效协同 · 安全合规 · 赋能企业财务数字化
              </p>
            </div>
          </div>

          {/* 底部：版本信息 */}
          <footer className="flex items-center justify-between text-body-sm text-blue-200/60">
            {/* <span>私有化部署 · v1.0</span> */}
            <span>© Finance AI Agent</span>
          </footer>
        </aside>

        {/* ============ 右侧登录卡片 ============ */}
        <main className="flex items-center justify-center p-6 sm:p-12">
          <div className="w-full max-w-lg">
            {/* 玻璃拟态卡片 */}
            <div className="rounded-2xl bg-white/95 backdrop-blur-md shadow-2xl shadow-blue-900/30 p-10 space-y-7 border border-white/60">
              {/* 卡片顶部：logo + 标题 */}
              <header className="flex items-start gap-3">
                <img
                  src={logoPng}
                  alt="logo"
                  className="h-20 w-20 shrink-0 object-contain"
                />
                <div className="flex flex-col leading-tight pt-1">
                  <div className="text-headline-lg font-bold text-slate-900">
                    企业AI Agent 财务平台
                  </div>
                  <p className="text-body-md text-slate-500 mt-1">
                    智能财务 · 让企业更有未来
                  </p>
                </div>
              </header>

              {/* 登录表单 */}
              <form
                onSubmit={form.handleSubmit((data) => login(data))}
                className="space-y-5"
                noValidate
              >
                {/* 账号 */}
                <div className="space-y-1.5">
                  <div className="relative">
                    <User2 className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400 pointer-events-none" />
                    <Input
                      id="account"
                      placeholder="请输入账号"
                      className="h-12 pl-12 pr-4 text-body-lg rounded-lg border-slate-200 bg-slate-50/60 focus-visible:bg-white"
                      autoComplete="username"
                      {...form.register('account')}
                      invalid={!!form.formState.errors.account}
                      disabled={isLoading}
                    />
                  </div>
                  {form.formState.errors.account && (
                    <p className="text-body-sm text-rose-500 pl-1">
                      {form.formState.errors.account.message}
                    </p>
                  )}
                </div>

                {/* 密码 */}
                <div className="space-y-1.5">
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400 pointer-events-none" />
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      placeholder="请输入密码"
                      className="h-12 pl-12 pr-12 text-body-lg rounded-lg border-slate-200 bg-slate-50/60 focus-visible:bg-white"
                      autoComplete="current-password"
                      {...form.register('password')}
                      invalid={!!form.formState.errors.password}
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((s) => !s)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                      tabIndex={-1}
                      aria-label={showPassword ? '隐藏密码' : '显示密码'}
                    >
                      {showPassword ? (
                        <EyeOff className="h-5 w-5" />
                      ) : (
                        <Eye className="h-5 w-5" />
                      )}
                    </button>
                  </div>
                  {form.formState.errors.password && (
                    <p className="text-body-sm text-rose-500 pl-1">
                      {form.formState.errors.password.message}
                    </p>
                  )}
                </div>

                {/* 记住我 + 忘记密码 */}
                <div className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2 cursor-pointer select-none group">
                    <Checkbox
                      checked={rememberMe}
                      onCheckedChange={(v) => setRememberMe(v === true)}
                      className="border-slate-300 data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
                    />
                    <span className="text-body-md text-slate-600 group-hover:text-slate-900">
                      记住我
                    </span>
                  </label>
                  <button
                    type="button"
                    className="text-body-md text-sky-500 hover:text-sky-600 hover:underline"
                  >
                    忘记密码？
                  </button>
                </div>

                {/* 登录按钮 */}
                <Button
                  type="submit"
                  size="lg"
                  className="w-full h-12 text-body-lg font-semibold rounded-lg bg-gradient-to-r from-sky-500 to-blue-500 hover:from-sky-600 hover:to-blue-600 text-white shadow-lg shadow-sky-500/30"
                  disabled={isLoading}
                >
                  {isLoading ? '登录中...' : '登录'}
                </Button>
              </form>

              {/* 默认账号提示（更柔和） */}
              <div className="rounded-lg border border-slate-200/70 bg-slate-50/60 p-3.5">
                <p className="text-label-sm font-semibold uppercase tracking-wider text-slate-500 mb-2">
                  默认测试账号
                </p>
                <div className="grid grid-cols-3 gap-2 text-body-sm">
                  <div>
                    <p className="font-mono font-semibold text-slate-700">
                      admin
                    </p>
                    <p className="text-slate-500 text-xs">Admin@123</p>
                  </div>
                  <div>
                    <p className="font-mono font-semibold text-slate-700">
                      finance01
                    </p>
                    <p className="text-slate-500 text-xs">Finance@123</p>
                  </div>
                  <div>
                    <p className="font-mono font-semibold text-slate-700">
                      employee01
                    </p>
                    <p className="text-slate-500 text-xs">Emp@123</p>
                  </div>
                </div>
              </div>

              <p className="text-center text-body-sm text-slate-400">
                首次登录将强制修改密码
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}