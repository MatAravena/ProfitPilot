import { create } from 'zustand'
import type { Position, PortfolioSnapshot } from '@/types'

interface PortfolioStore {
  equity: number
  cashBalance: number
  dailyPnl: number
  totalPnl: number
  drawdown: number
  positions: Position[]
  lastUpdatedAt: number | null
  setSnapshot: (snapshot: PortfolioSnapshot) => void
  updatePosition: (position: Position) => void
}

export const usePortfolioStore = create<PortfolioStore>((set) => ({
  equity: 0,
  cashBalance: 0,
  dailyPnl: 0,
  totalPnl: 0,
  drawdown: 0,
  positions: [],
  lastUpdatedAt: null,

  setSnapshot: (snapshot) =>
    set({
      equity: snapshot.equity,
      cashBalance: snapshot.cashBalance,
      dailyPnl: snapshot.dailyPnl,
      totalPnl: snapshot.totalPnl,
      drawdown: snapshot.drawdown,
      positions: snapshot.positions,
      lastUpdatedAt: snapshot.updatedAt,
    }),

  updatePosition: (position) =>
    set((state) => ({
      positions: state.positions.map((p) => (p.id === position.id ? position : p)),
    })),
}))
