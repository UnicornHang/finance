import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Search, Users } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader } from '@/components/ui/stat'
import { Table, TBody, TD, TH, THead, TR, EmptyState, Toolbar } from '@/components/ui/table'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { userApi } from '@/api/admin'
import { UserFormDialog, type UserFormValues } from '@/components/admin/UserFormDialog'
import { apiErrorMessage, formatDate } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types'

const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  finance: '财务',
  employee: '员工',
}

const ROLE_TONE: Record<string, 'primary' | 'success' | 'neutral'> = {
  admin: 'primary',
  finance: 'success',
  employee: 'neutral',
}

const STATUS_TONE: Record<string, 'success' | 'warning' | 'danger'> = {
  active: 'success',
  locked: 'warning',
  disabled: 'danger',
}

const STATUS_LABEL: Record<string, string> = {
  active: '启用',
  locked: '锁定',
  disabled: '停用',
}

type ConfirmAction = 'reset' | 'disable' | 'enable'

/** 后台用户管理：列表筛选与增删改、重置密码。 */
export function UserManage() {
  const queryClient = useQueryClient()
  const currentUserId = useAuthStore((s) => s.user?.id)
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => userApi.list(),
  })

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [editing, setEditing] = useState<User | null>(null)
  const [confirmUser, setConfirmUser] = useState<User | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null)
  const [tempPassword, setTempPassword] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['users'] })

  const createMutation = useMutation({
    mutationFn: (values: UserFormValues) =>
      userApi.create({
        name: values.name.trim(),
        account: values.account.trim(),
        password: values.password,
        role: values.role,
        dept: values.dept.trim() || null,
      }),
    onSuccess: () => {
      toast.success('用户已创建')
      setFormOpen(false)
      invalidate()
    },
    onError: (error) => toast.error(apiErrorMessage(error, '创建失败')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: UserFormValues }) =>
      userApi.update(id, {
        name: values.name.trim(),
        role: values.role,
        dept: values.dept.trim() || null,
        status: values.status,
      }),
    onSuccess: () => {
      toast.success('用户已更新')
      setFormOpen(false)
      setEditing(null)
      invalidate()
    },
    onError: (error) => toast.error(apiErrorMessage(error, '更新失败')),
  })

  const resetMutation = useMutation({
    mutationFn: (id: string) => userApi.resetPassword(id),
    onSuccess: (data) => {
      setTempPassword(data.temporary_password)
      toast.success('已生成临时密码')
      invalidate()
    },
    onError: (error) => toast.error(apiErrorMessage(error, '重置失败')),
  })

  const disableMutation = useMutation({
    mutationFn: (id: string) => userApi.remove(id),
    onSuccess: () => {
      toast.success('用户已停用')
      invalidate()
    },
    onError: (error) => toast.error(apiErrorMessage(error, '停用失败')),
  })

  const enableMutation = useMutation({
    mutationFn: (id: string) => userApi.update(id, { status: 'active' }),
    onSuccess: () => {
      toast.success('用户已启用')
      invalidate()
    },
    onError: (error) => toast.error(apiErrorMessage(error, '启用失败')),
  })

  const list = (users || []).filter((u) => {
    if (roleFilter !== 'all' && u.role !== roleFilter) return false
    if (statusFilter !== 'all' && u.status !== statusFilter) return false
    if (search && !`${u.name} ${u.account}`.toLowerCase().includes(search.toLowerCase())) {
      return false
    }
    return true
  })

  /** 打开新增弹窗。 */
  const openCreate = () => {
    setFormMode('create')
    setEditing(null)
    setFormOpen(true)
  }

  /** 打开编辑弹窗。 */
  const openEdit = (user: User) => {
    setFormMode('edit')
    setEditing(user)
    setFormOpen(true)
  }

  /** 提交新增或编辑。 */
  const handleFormSubmit = async (values: UserFormValues) => {
    if (formMode === 'create') {
      await createMutation.mutateAsync(values)
      return
    }
    if (!editing) return
    await updateMutation.mutateAsync({ id: editing.id, values })
  }

  /** 执行二次确认后的重置 / 停用 / 启用。 */
  const handleConfirm = async () => {
    if (!confirmUser || !confirmAction) return
    const target = confirmUser
    setConfirmUser(null)
    setConfirmAction(null)
    if (confirmAction === 'reset') {
      await resetMutation.mutateAsync(target.id)
      return
    }
    if (confirmAction === 'disable') {
      await disableMutation.mutateAsync(target.id)
      return
    }
    await enableMutation.mutateAsync(target.id)
  }

  /** 复制临时密码到剪贴板。 */
  const copyTempPassword = async () => {
    if (!tempPassword) return
    try {
      await navigator.clipboard.writeText(tempPassword)
      toast.success('已复制临时密码')
    } catch {
      toast.error('复制失败，请手动复制')
    }
  }

  const confirmCopy: Record<
    ConfirmAction,
    { title: string; description: string; action: string }
  > = {
    reset: {
      title: '重置密码？',
      description: `将为 ${confirmUser?.name} 生成一次性临时密码，原密码立即失效。`,
      action: '重置',
    },
    disable: {
      title: '停用该账号？',
      description: `${confirmUser?.name}（${confirmUser?.account}）停用后无法登录，历史单据仍保留。`,
      action: '停用',
    },
    enable: {
      title: '重新启用？',
      description: `恢复 ${confirmUser?.name} 的登录权限，并解除登录锁定。`,
      action: '启用',
    },
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        actions={
          <Button size="md" onClick={openCreate}>
            <Plus className="h-4 w-4" />
            新增用户
          </Button>
        }
      />

      <Card>
        <Toolbar>
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-tertiary" />
            <Input
              placeholder="搜索姓名 / 账号"
              className="h-9 pl-8"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select value={roleFilter} onValueChange={setRoleFilter}>
            <SelectTrigger className="h-9 w-40">
              <SelectValue placeholder="全部角色" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部角色</SelectItem>
              <SelectItem value="admin">管理员</SelectItem>
              <SelectItem value="finance">财务</SelectItem>
              <SelectItem value="employee">员工</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-9 w-40">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="active">启用</SelectItem>
              <SelectItem value="locked">锁定</SelectItem>
              <SelectItem value="disabled">停用</SelectItem>
            </SelectContent>
          </Select>
          <span className="ml-auto text-body-sm text-ink-tertiary tabular-nums">
            共 {list.length} 个账号
          </span>
        </Toolbar>

        <CardContent className="p-0">
          {isLoading ? (
            <EmptyState icon={<Users className="h-5 w-5" />} title="加载中..." />
          ) : list.length === 0 ? (
            <EmptyState
              icon={<Users className="h-5 w-5" />}
              title="暂无用户"
              description="新增用户以分配角色与权限"
            />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>姓名</TH>
                  <TH>账号</TH>
                  <TH>角色</TH>
                  <TH>部门</TH>
                  <TH>状态</TH>
                  <TH>创建时间</TH>
                  <TH className="text-right">操作</TH>
                </TR>
              </THead>
              <TBody>
                {list.map((u) => (
                  <TR key={u.id}>
                    <TD>
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-tint text-primary text-label-md font-semibold">
                          {u.name?.[0] || 'U'}
                        </div>
                        <span className="font-semibold">{u.name}</span>
                      </div>
                    </TD>
                    <TD className="font-mono text-body-sm">{u.account}</TD>
                    <TD>
                      <Badge tone={ROLE_TONE[u.role] || 'neutral'} dot>
                        {ROLE_LABEL[u.role] || u.role}
                      </Badge>
                    </TD>
                    <TD className="text-ink-secondary">{u.dept || '-'}</TD>
                    <TD>
                      <Badge tone={STATUS_TONE[u.status] || 'neutral'} dot>
                        {STATUS_LABEL[u.status] || u.status}
                      </Badge>
                    </TD>
                    <TD className="text-ink-tertiary">{formatDate(u.created_at)}</TD>
                    <TD className="text-right">
                      <div className="inline-flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openEdit(u)}>
                          编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setConfirmUser(u)
                            setConfirmAction('reset')
                          }}
                        >
                          重置密码
                        </Button>
                        {u.status === 'disabled' ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setConfirmUser(u)
                              setConfirmAction('enable')
                            }}
                          >
                            启用
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-danger hover:bg-danger-tint hover:text-danger"
                            disabled={u.id === currentUserId}
                            onClick={() => {
                              setConfirmUser(u)
                              setConfirmAction('disable')
                            }}
                          >
                            停用
                          </Button>
                        )}
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <UserFormDialog
        open={formOpen}
        mode={formMode}
        user={editing}
        submitting={createMutation.isPending || updateMutation.isPending}
        onOpenChange={setFormOpen}
        onSubmit={handleFormSubmit}
      />

      <AlertDialog
        open={!!confirmUser && !!confirmAction}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmUser(null)
            setConfirmAction(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction ? confirmCopy[confirmAction].title : ''}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction ? confirmCopy[confirmAction].description : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className={confirmAction === 'disable' ? 'bg-danger hover:bg-danger-hover' : undefined}
              onClick={handleConfirm}
            >
              {confirmAction ? confirmCopy[confirmAction].action : '确定'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={!!tempPassword} onOpenChange={(open) => !open && setTempPassword(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>临时密码</DialogTitle>
            <DialogDescription>
              请立即复制并告知用户，关闭后无法再次查看明文。
            </DialogDescription>
          </DialogHeader>
          <p className="rounded-md bg-surface-inset px-3 py-2 font-mono text-body-md break-all">
            {tempPassword}
          </p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setTempPassword(null)}>
              关闭
            </Button>
            <Button onClick={copyTempPassword}>复制</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
