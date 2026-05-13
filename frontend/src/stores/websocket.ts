import { create } from 'zustand'

type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface WebSocketStore {
  status: WSStatus
  subscribedSymbols: string[]
  lastPing: number | null
  setStatus: (status: WSStatus) => void
  subscribe: (channel: string) => void
  unsubscribe: (channel: string) => void
}

export const useWebSocketStore = create<WebSocketStore>((set) => ({
  status: 'disconnected',
  subscribedSymbols: [],
  lastPing: null,

  setStatus: (status) => set({ status }),

  subscribe: (channel) =>
    set((s) => ({
      subscribedSymbols: s.subscribedSymbols.includes(channel)
        ? s.subscribedSymbols
        : [...s.subscribedSymbols, channel],
    })),

  unsubscribe: (channel) =>
    set((s) => ({
      subscribedSymbols: s.subscribedSymbols.filter((c) => c !== channel),
    })),
}))
