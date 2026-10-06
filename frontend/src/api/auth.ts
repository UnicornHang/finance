import { apiClient } from './client'
import type { User } from '@/types'

export interface ProfileUpdatePayload {
  name?: string
  dept?: string | null
}

export interface PasswordChangePayload {
  old_password: string
  new_password: string
}

/** 当前登录用户的资料与改密接口。 */
export const authApi = {
  me: () => apiClient.get<User>('/auth/me').then((r) => r.data),
  updateProfile: (data: ProfileUpdatePayload) =>
    apiClient.patch<User>('/auth/me', data).then((r) => r.data),
  changePassword: (data: PasswordChangePayload) =>
    apiClient.post<{ message: string }>('/auth/me/password', data).then((r) => r.data),
}
