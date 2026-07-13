import { describe, it, expect } from 'vitest'
import { buildTradeMarkers } from './tradeMarkers'
import type { TradeRecord } from '@/types/backtest'

const trade = (over: Partial<TradeRecord>): TradeRecord => ({
  symbol: 'BTCUSDT', side: 'long', entry_price: 100, exit_price: 110, size: 1,
  pnl: 10, pnl_pct: 10, entry_time: 1_700_000_000_000, exit_time: 1_700_086_400_000, ...over,
})

describe('buildTradeMarkers', () => {
  it('maps a long trade to buy-at-entry then sell-at-exit', () => {
    const m = buildTradeMarkers([trade({ side: 'long' })])
    expect(m).toHaveLength(2)
    expect(m[0]).toMatchObject({ shape: 'arrowUp', position: 'belowBar', time: 1_700_000_000 })
    expect(m[1]).toMatchObject({ shape: 'arrowDown', position: 'aboveBar', time: 1_700_086_400 })
  })

  it('maps a short trade to sell-at-entry then buy-at-exit', () => {
    const m = buildTradeMarkers([trade({ side: 'short' })])
    expect(m[0]).toMatchObject({ shape: 'arrowDown', position: 'aboveBar' })
    expect(m[1]).toMatchObject({ shape: 'arrowUp', position: 'belowBar' })
  })

  it('returns markers sorted ascending by time across trades', () => {
    const m = buildTradeMarkers([
      trade({ entry_time: 1_700_200_000_000, exit_time: 1_700_300_000_000 }),
      trade({ entry_time: 1_700_000_000_000, exit_time: 1_700_100_000_000 }),
    ])
    const times = m.map((x) => x.time as number)
    expect(times).toEqual([...times].sort((a, b) => a - b))
  })
})
