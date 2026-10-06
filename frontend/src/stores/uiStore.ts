import { create } from 'zustand'
import type { Invoice } from '@/types'

/**
 * 发票侧弹窗数据形态：
 * - 处理中：{ status: 'processing'; file_url; file_hash }
 * - 就绪：  { status: 'ready'; invoice_id; ...Invoice }
 * - 兼容老：Plain Invoice fields（无 status 标记）
 */
export type InvoiceSidePanelData =
  | { status: 'processing'; file_url: string; file_hash: string }
  | ({
      status: 'ready'
      invoice_id: string
      /** pending=待确认归档；archived=已归档。UI 的 status 固定为 ready，入库态走此字段。 */
      archive_status?: 'pending' | 'archived' | string | null
    } & Partial<Invoice>)
  | (Partial<Invoice> & {
      invoice_id?: string
      status?: string
      archive_status?: 'pending' | 'archived' | string | null
    })

/**
 * 全局 sidePanelData 类型：宽松 any 以兼容多类侧弹窗（合同/发票）
 * 业务组件内部自行收窄类型（InvoiceSidePanelData / ContractData / ...）
 */
export type SidePanelData = unknown

interface UIState {
  sidePanelOpen: boolean
  sidePanelType: 'invoice' | 'contract' | null
  sidePanelData: SidePanelData
  streaming: boolean
  /** Chat 左侧会话栏是否收起（DeepSeek 风：可整页折叠给主区更多空间） */
  sidebarCollapsed: boolean

  openSidePanel: (type: 'invoice' | 'contract', data: SidePanelData) => void
  /** 只收起面板，保留内容，便于「重新打开」 */
  closeSidePanel: () => void
  /** 切会话或归档完成后清空，侧栏不再可重开 */
  clearSidePanel: () => void
  /** 用当前缓存的 type/data 再次展开 */
  reopenSidePanel: () => void
  setStreaming: (streaming: boolean) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  sidePanelOpen: false,
  sidePanelType: null,
  sidePanelData: null,
  streaming: false,
  sidebarCollapsed: false,

  openSidePanel: (type, data) =>
    set({ sidePanelOpen: true, sidePanelType: type, sidePanelData: data }),
  closeSidePanel: () => set({ sidePanelOpen: false }),
  clearSidePanel: () =>
    set({ sidePanelOpen: false, sidePanelType: null, sidePanelData: null }),
  reopenSidePanel: () => {
    const { sidePanelType, sidePanelData } = get()
    if (sidePanelType && sidePanelData != null) {
      set({ sidePanelOpen: true })
    }
  },
  setStreaming: (streaming) => set({ streaming }),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}))
