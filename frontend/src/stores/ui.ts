import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'

interface UIStore {
  sidebarCollapsed: boolean
  activeTimeframe: Timeframe
  openModal: string | null
  toggleSidebar: () => void
  setTimeframe: (tf: Timeframe) => void
  showModal: (id: string) => void
  closeModal: () => void
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      activeTimeframe: '1h',
      openModal: null,

      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setTimeframe: (tf) => set({ activeTimeframe: tf }),
      showModal: (id) => set({ openModal: id }),
      closeModal: () => set({ openModal: null }),
    }),
    {
      name: 'profitpilot-ui',
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, activeTimeframe: s.activeTimeframe }),
    },
  ),
)
