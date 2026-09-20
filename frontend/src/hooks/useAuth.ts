import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { apiClient } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types'

interface LoginPayload {
  account: string
  password: string
}

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export function useAuth() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const logout = useAuthStore((s) => s.logout)

  const loginMutation = useMutation({
    mutationFn: async (payload: LoginPayload) => {
      // OAuth2PasswordRequestForm 需要 application/x-www-form-urlencoded
      const params = new URLSearchParams()
      params.append('username', payload.account)
      params.append('password', payload.password)
      const { data } = await apiClient.post<LoginResponse>(
        '/auth/login',
        params.toString(),
        {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        },
      )
      return data
    },
    onSuccess: (data) => {
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      setAuth(data.access_token, data.refresh_token, data.user)
      toast.success(`欢迎回来，${data.user.name}`)
      navigate('/chat')
    },
    onError: (err: any) => {
      const message =
        err?.response?.data?.message || '账号或密码错误，请重试'
      toast.error(message)
    },
  })

  return {
    login: loginMutation.mutate,
    isLoading: loginMutation.isPending,
    logout: () => {
      logout()
      navigate('/login')
    },
  }
}