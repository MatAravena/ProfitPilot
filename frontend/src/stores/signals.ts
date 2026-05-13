import { create } from 'zustand'
import type { SignalRecord } from '@/types'

const MAX_LIVE_SIGNALS = 50

interface SignalsStore {
  liveSignals: SignalRecord[]
  pushSignal: (signal: SignalRecord) => void
  setSignals: (signals: SignalRecord[]) => void
}

export const useSignalsStore = create<SignalsStore>((set) => ({
  liveSignals: [],

  pushSignal: (signal) =>
    set((s) => ({
      liveSignals: [signal, ...s.liveSignals].slice(0, MAX_LIVE_SIGNALS),
    })),

  setSignals: (signals) => set({ liveSignals: signals }),
}))
