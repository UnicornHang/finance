import { useEffect, useState } from 'react'

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { User, UserRole } from '@/types'

export type UserFormValues = {
  name: string
  account: string
  password: string
  role: UserRole
  dept: string
  status: 'active' | 'disabled'
}

type UserFormDialogProps = {
  open: boolean
  mode: 'create' | 'edit'
  user: User | null
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (values: UserFormValues) => Promise<void>
}

const EMPTY_VALUES: UserFormValues = {
  name: '',
  account: '',
  password: '',
  role: 'employee',
  dept: '',
  status: 'active',
}

/** 新增 / 编辑用户弹窗。 */
export function UserFormDialog({
  open,
  mode,
  user,
  submitting,
  onOpenChange,
  onSubmit,
}: UserFormDialogProps) {
  const [values, setValues] = useState<UserFormValues>(EMPTY_VALUES)

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && user) {
      setValues({
        name: user.name,
        account: user.account,
        password: '',
        role: user.role,
        dept: user.dept || '',
        status: user.status === 'disabled' ? 'disabled' : 'active',
      })
      return
    }
    setValues(EMPTY_VALUES)
  }, [open, mode, user])

  /** 提交前做前端必填校验。 */
  const handleSubmit = async () => {
    if (!values.name.trim() || !values.account.trim()) return
    if (mode === 'create' && values.password.length < 10) return
    await onSubmit(values)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? '新增用户' : '编辑用户'}</DialogTitle>
          <DialogDescription>
            {mode === 'create'
              ? '创建账号并分配角色，密码至少 10 位。'
              : '可调整姓名、角色、部门与启用状态。账号不可修改。'}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div>
            <Label htmlFor="user-name" required>
              姓名
            </Label>
            <Input
              id="user-name"
              value={values.name}
              onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
              placeholder="显示名称"
            />
          </div>
          <div>
            <Label htmlFor="user-account" required>
              账号
            </Label>
            <Input
              id="user-account"
              value={values.account}
              disabled={mode === 'edit'}
              onChange={(e) => setValues((v) => ({ ...v, account: e.target.value }))}
              placeholder="登录账号"
              autoComplete="off"
            />
          </div>
          {mode === 'create' && (
            <div>
              <Label htmlFor="user-password" required>
                初始密码
              </Label>
              <Input
                id="user-password"
                type="password"
                value={values.password}
                onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
                placeholder="至少 10 位"
                autoComplete="new-password"
              />
            </div>
          )}
          <div>
            <Label required>角色</Label>
            <Select
              value={values.role}
              onValueChange={(role) =>
                setValues((v) => ({ ...v, role: role as UserRole }))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="employee">员工</SelectItem>
                <SelectItem value="finance">财务</SelectItem>
                <SelectItem value="admin">管理员</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="user-dept">部门</Label>
            <Input
              id="user-dept"
              value={values.dept}
              onChange={(e) => setValues((v) => ({ ...v, dept: e.target.value }))}
              placeholder="可选"
            />
          </div>
          {mode === 'edit' && (
            <div>
              <Label>状态</Label>
              <Select
                value={values.status}
                onValueChange={(status) =>
                  setValues((v) => ({
                    ...v,
                    status: status as 'active' | 'disabled',
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">启用</SelectItem>
                  <SelectItem value="disabled">停用</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            取消
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={
              submitting ||
              !values.name.trim() ||
              !values.account.trim() ||
              (mode === 'create' && values.password.length < 10)
            }
          >
            {submitting ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
