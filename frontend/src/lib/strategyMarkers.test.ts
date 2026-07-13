import { describe, it, expect } from 'vitest'
import { buildStrategyMarkers } from './strategyMarkers'
import type { OrderRecord, SignalRecord } from '@/types'

const order = (over: Partial<OrderRecord>): OrderRecord => ({
  id: 'o', symbol: 'BTCUSDT', side: 'buy', quantity: 0.1, status: 'opened_long',
  reason: null, avg_price: 30000, filled_qty: 0.1, realized_pnl: null,
  signal_id: null, created_at: '2024-01-01T00:00:00Z', ...over,
})

describe('buildStrategyMarkers', () => {
  it('maps buy fills to up arrows and sell fills to down arrows', () => {
    const m = buildStrategyMarkers({
      orders: [order({ side: 'buy' }), order({ side: 'sell', created_at: '2024-01-02T00:00:00Z' })],
      signals: [],
    })
    expect(m).toHaveLength(2)
    expect(m[0]).toMatchObject({ shape: 'arrowUp', position: 'belowBar' })
    expect(m[1]).toMatchObject({ shape: 'arrowDown', position: 'aboveBar' })
  })

  it('skips order rows that never filled', () => {
    const m = buildStrategyMarkers({
      orders: [order({ status: 'rejected', filled_qty: null, avg_price: null })],
      signals: [],
    })
    expect(m).toHaveLength(0)
  })

  it('includes faint signal markers only when showSignals is true', () => {
    const signals: SignalRecord[] = [{
      id: 's', strategy_instance_id: 'x', symbol: 'BTCUSDT', timeframe: '1d',
      direction: 'long', confidence: 0.7, source: 'quant',
      generated_at: '2024-01-03T00:00:00Z', close_price: 100,
    }]
    expect(buildStrategyMarkers({ orders: [], signals }).length).toBe(0)
    expect(buildStrategyMarkers({ orders: [], signals, showSignals: true }).length).toBe(1)
  })

  it('adds a projected marker for the latest signal', () => {
    const m = buildStrategyMarkers({
      orders: [], signals: [], latestSignal: { direction: 'long', time: 1704067200 },
    })
    expect(m).toHaveLength(1)
    expect(m[0]).toMatchObject({ color: '#3b82f6', shape: 'arrowUp' })
  })

  it('returns markers sorted ascending by time', () => {
    const m = buildStrategyMarkers({
      orders: [order({ created_at: '2024-01-05T00:00:00Z' }), order({ created_at: '2024-01-01T00:00:00Z' })],
      signals: [],
    })
    expect(m[0].time as number).toBeLessThan(m[1].time as number)
  })
})
