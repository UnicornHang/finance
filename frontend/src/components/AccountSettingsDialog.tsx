import { useEffect, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { toast } from 'sonner'

import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useAuthStore } from '@/stores/authStore'

const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  finance: '财务',
  employee: '员工',
}

type AccountSettingsDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** 当前用户账户设置：改姓名/部门、修改登录密码。 */
export function AccountSettingsDialog({
  open,
  onOpenChange,
}: AccountSettingsDialogProps) {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)

  const [name, setName] = useState('')
  const [dept, setDept] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    if (!open || !user) return
    setName(user.name)
    setDept(user.dept || '')
    setOldPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setShowPasswords(false)
  }, [open, user])

  /** 保存姓名与部门，账号和角色只读。 */
  const handleSaveProfile = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      toast.error('姓名不能为空')
      return
    }
    setSavingProfile(true)
    try {
      const updated = await authApi.updateProfile({
        name: trimmed,
        dept: dept.trim() || null,
      })
      setUser(updated)
      toast.success('资料已更新')
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || '资料更新失败'
      toast.error(message)
    } finally {
      setSavingProfile(false)
    }
  }

  /** 校验并提交改密。 */
  const handleChangePassword = async () => {
    if (!oldPassword) {
      toast.error('请输入当前密码')
      return
    }
    if (newPassword.length < 10) {
      toast.error('新密码至少 10 位')
      return
    }
    if (newPassword !== confirmPassword) {
      toast.error('两次输入的新密码不一致')
      return
    }
    setSavingPassword(true)
    try {
      await authApi.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      })
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.success('密码已更新')
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data
          ?.message || '密码修改失败'
      toast.error(message)
    } finally {
      setSavingPassword(false)
    }
  }

  const busy = savingProfile || savingPassword

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>账户设置</DialogTitle>
          <DialogDescription>
            可修改显示姓名与部门，或更换登录密码。账号与角色由管理员分配。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div>
            <Label htmlFor="account-login">账号</Label>
            <Input id="account-login" value={user?.account || ''} disabled />
          </div>
          <div>
            <Label htmlFor="account-role">角色</Label>
            <Input
              id="account-role"
              value={ROLE_LABEL[user?.role || ''] || user?.role || ''}
              disabled
            />
          </div>
          <div>
            <Label htmlFor="account-name" required>
              姓名
            </Label>
            <Input
              id="account-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="显示名称"
              autoComplete="name"
            />
          </div>
          <div>
            <Label htmlFor="account-dept">部门</Label>
            <Input
              id="account-dept"
              value={dept}
              onChange={(e) => setDept(e.target.value)}
              placeholder="可选"
            />
          </div>
          <Button
            type="button"
            onClick={handleSaveProfile}
            disabled={busy || !name.trim()}
          >
            {savingProfile ? '保存中...' : '保存资料'}
          </Button>

          <Separator />

          <div className="flex items-center justify-between">
            <p className="text-body-sm font-semibold text-ink">修改密码</p>
            <button
              type="button"
              className="text-ink-tertiary hover:text-ink"
              onClick={() => setShowPasswords((v) => !v)}
              aria-label={showPasswords ? '隐藏密码' : '显示密码'}
            >
              {showPasswords ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
          <div>
            <Label htmlFor="account-old-password" required>
              当前密码
            </Label>
            <Input
              id="account-old-password"
              type={showPasswords ? 'text' : 'password'}
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div>
            <Label htmlFor="account-new-password" required>
              新密码
            </Label>
            <Input
              id="account-new-password"
              type={showPasswords ? 'text' : 'password'}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="至少 10 位"
              autoComplete="new-password"
            />
          </div>
          <div>
            <Label htmlFor="account-confirm-password" required>
              确认新密码
            </Label>
            <Input
              id="account-confirm-password"
              type={showPasswords ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={handleChangePassword}
            disabled={busy}
          >
            {savingPassword ? '提交中...' : '更新密码'}
          </Button>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
