import { create } from 'zustand'

interface UIState {
  sidePanelOpen: boolean
  sidePanelType: 'invoice' | 'contract' | null
  sidePanelData: any
  streaming: boolean

  openSidePanel: (type: 'invoice' | 'contract', data: any) => void
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