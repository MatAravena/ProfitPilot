import { create } from 'zustand'
import type { Strategy, StrategyStatusUpdate } from '@/types'

interface StrategyStore {
  strategies: Strategy[]
  activeStrategyId: string | null
  setStrategies: (strategies: Strategy[]) => void
  updateStatus: (id: string, status: StrategyStatusUpdate) => void
  setActiveStrategy: (id: string | null) => void
}

export const useStrategyStore = create<StrategyStore>((set) => ({
  strategies: [],
  activeStrategyId: null,

  setStrategies: (strategies) => set({ strategies }),

  updateStatus: (id, status) =>
    set((state) => ({
      strategies: state.strategies.map((s) =>
        s.id === id ? { ...s, status: status.status, lastSignalAt: status.lastSignalAt } : s,
      ),
    })),

  setActiveStrategy: (id) => set({ activeStrategyId: id }),
}))
