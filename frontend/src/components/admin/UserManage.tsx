import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search, UserCog, Users } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SectionHeader } from '@/components/ui/stat'
import { Table, TBody, TD, TH, THead, TR, EmptyState, Toolbar } from '@/components/ui/table'
import { userApi } from '@/api/admin'
import { formatDate } from '@/lib/utils'

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

export function UserManage() {
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => userApi.list(),
  })

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')

  const list = (users || []).filter((u) => {
    if (roleFilter && u.role !== roleFilter) return false
    if (search && !`${u.name} ${u.account}`.toLowerCase().includes(search.toLowerCase()))
      return false
    return true
  })

  return (
    <div className="space-y-6">
      <SectionHeader
        title="权限"
        description="管理企业内部账号、角色与组织归属"
        actions={
          <Button size="md">
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
          <Select
            className="h-9 w-40"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">全部角色</option>
            <option value="admin">管理员</option>
            <option value="finance">财务</option>
            <option value="employee">员工</option>
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
                      <button
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-label-md text-ink-secondary hover:bg-surface-inset hover:text-ink"
                        aria-label="编辑"
                      >
                        <UserCog className="h-3.5 w-3.5" />
                        编辑
                      </button>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}