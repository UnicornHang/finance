import { queryClient } from '@/lib/queryClient'
import { useSessionStore } from '@/stores/sessionStore'
import { useUIStore } from '@/stores/uiStore'

/**
 * 退出或换账号时清掉本机业务缓存。
 * 会话 store 不随 persist，不重置的话下一账号会继续请求上一账号的 sessionId。
 */
export function resetClientState() {
  useSessionStore.getState().reset()
  useUIStore.getState().clearSidePanel()
  useUIStore.getState().setStreaming(false)
  queryClient.clear()
}
