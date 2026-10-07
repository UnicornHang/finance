import { Navigate, Route, Routes } from 'react-router-dom'

import { Login } from '@/pages/Login'
import { Chat } from '@/pages/Chat'
import { Admin } from '@/pages/Admin'
import { Dashboard } from '@/components/admin/Dashboard'
import { InvoiceArchive } from '@/components/admin/InvoiceArchive'
import { ContractArchive } from '@/components/admin/ContractArchive'
import { KnowledgeBase } from '@/components/admin/KnowledgeBase'
import { KnowledgeBaseDetail } from '@/components/admin/KnowledgeBaseDetail'
import { UserManage } from '@/components/admin/UserManage'
import { AuditLogs } from '@/components/admin/AuditLogs'
import { LLMSettings } from '@/components/admin/LLMSettings'
import { ToolSettings } from '@/components/admin/ToolSettings'
import { useAuthStore } from '@/stores/authStore'
import type { UserRole } from '@/types'

/** 无权限时的后台默认落地页 */
function adminFallback(role: UserRole | undefined): string {
  if (role === 'employee') return '/admin/invoices'
  return '/admin'
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const hasHydrated = useAuthStore((s) => s.hasHydrated)
  const isAuthed = useAuthStore((s) => !!s.token)
  if (!hasHydrated) return null
  if (!isAuthed) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** 按角色守卫路由；无权则跳到该角色可用的后台首页 */
function RoleRoute({
  roles,
  children,
}: {
  roles: UserRole[]
  children: React.ReactNode
}) {
  const role = useAuthStore((s) => s.user?.role)
  if (!role || !roles.includes(role)) {
    return <Navigate to={adminFallback(role)} replace />
  }
  return <>{children}</>
}

/** 数据概览：员工无权限，直接落到发票归档 */
function AdminHome() {
  const role = useAuthStore((s) => s.user?.role)
  if (role === 'employee') {
    return <Navigate to="/admin/invoices" replace />
  }
  return <Dashboard />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/chat/*"
        element={
          <ProtectedRoute>
            <Chat />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <ProtectedRoute>
            <Admin />
          </ProtectedRoute>
        }
      >
        <Route index element={<AdminHome />} />
        <Route path="invoices" element={<InvoiceArchive />} />
        <Route path="contracts" element={<ContractArchive />} />
        <Route
          path="kb"
          element={
            <RoleRoute roles={['admin']}>
              <KnowledgeBase />
            </RoleRoute>
          }
        />
        <Route
          path="kb/:id"
          element={
            <RoleRoute roles={['admin']}>
              <KnowledgeBaseDetail />
            </RoleRoute>
          }
        />
        <Route
          path="users"
          element={
            <RoleRoute roles={['admin']}>
              <UserManage />
            </RoleRoute>
          }
        />
        <Route
          path="audit"
          element={
            <RoleRoute roles={['admin']}>
              <AuditLogs />
            </RoleRoute>
          }
        />
        <Route
          path="llm"
          element={
            <RoleRoute roles={['admin']}>
              <LLMSettings />
            </RoleRoute>
          }
        />
        <Route
          path="tools"
          element={
            <RoleRoute roles={['admin']}>
              <ToolSettings />
            </RoleRoute>
          }
        />
      </Route>
      <Route path="/" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
