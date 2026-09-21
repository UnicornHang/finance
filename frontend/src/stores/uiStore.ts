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
  | ({ status: 'ready'; invoice_id: string } & Partial<Invoice>)
  | (Partial<Invoice> & { invoice_id?: string; status?: string })

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

  openSidePanel: (type: 'invoice' | 'contract', data: SidePanelData) => void
  closeSidePanel: () => void
  setStreaming: (streaming: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  sidePanelOpen: false,
  sidePanelType: null,
  sidePanelData: null,
  streaming: false,

  openSidePanel: (type, data) =>
    set({ sidePanelOpen: true, sidePanelType: type, sidePanelData: data }),
  closeSidePanel: () =>
    set({ sidePanelOpen: false, sidePanelType: null, sidePanelData: null }),
  setStreaming: (streaming) => set({ streaming }),
}))
