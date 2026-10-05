import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '@/types'

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: User | null
  /** persist 从 localStorage 恢复完毕；未完成前不要按「未登录」跳转 */
  hasHydrated: boolean
  setHasHydrated: (hasHydrated: boolean) => void
  setAuth: (token: string, refreshToken: string, user: User) => void
  setUser: (user: User) => void
  logout: () => void
}

function writeTokenPair(token: string, refreshToken: string) {
  localStorage.setItem('access_token', token)
  localStorage.setItem('refresh_token', refreshToken)
}

function clearTokenPair() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      hasHydrated: false,
      setHasHydrated: (hasHydrated) => set({ hasHydrated }),
      setAuth: (token, refreshToken, user) => {
        writeTokenPair(token, refreshToken)
        set({ token, refreshToken, user })
      },
      setUser: (user) => set({ user }),
      logout: () => {
        clearTokenPair()
        set({ token: null, refreshToken: null, user: null })
      },
    }),
    {
      name: 'finance-auth',
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        // 恢复完成（含无缓存）后再开放路由判断，避免空快照盖掉刚写入的登录态
        if (state?.token && state.refreshToken) {
          writeTokenPair(state.token, state.refreshToken)
        }
        state?.setHasHydrated(true)
      },
    },
  ),
)
