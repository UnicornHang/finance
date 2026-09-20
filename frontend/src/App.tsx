import { Navigate, Route, Routes } from 'react-router-dom'

import { Login } from '@/pages/Login'
import { Chat } from '@/pages/Chat'
import { Admin } from '@/pages/Admin'
import { Dashboard } from '@/components/admin/Dashboard'
import { InvoiceArchive } from '@/components/admin/InvoiceArchive'
import { ContractArchive } from '@/components/admin/ContractArchive'
import { KnowledgeBase } from '@/components/admin/KnowledgeBase'
import { UserManage } from '@/components/admin/UserManage'
import { LLMSettings } from '@/components/admin/LLMSettings'
import { useAuthStore } from '@/stores/authStore'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthed = useAuthStore((s) => !!s.token)
  if (!isAuthed) return <Navigate to="/login" replace />
  return <>{children}</>
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
        <Route index element={<Dashboard />} />
        <Route path="invoices" element={<InvoiceArchive />} />
        <Route path="contracts" element={<ContractArchive />} />
        <Route path="kb" element={<KnowledgeBase />} />
        <Route path="users" element={<UserManage />} />
        <Route path="llm" element={<LLMSettings />} />
      </Route>
      <Route path="/" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}