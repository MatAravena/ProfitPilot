import { describe, it, expect, beforeEach } from 'vitest'
import { useSignalsStore } from './signals'
import type { SignalRecord } from '@/types'

function makeSignal(id: string, overrides: Partial<SignalRecord> = {}): SignalRecord {
  return {
    id,
    strategy_instance_id: 'strat-1',
    symbol: 'BTCUSDT',
    timeframe: '1d',
    direction: 'long',
    confidence: 0.75,
    source: 'quant',
    generated_at: new Date().toISOString(),
    close_price: 50000,
    ...overrides,
  }
}

describe('useSignalsStore', () => {
  beforeEach(() => {
    useSignalsStore.setState({ liveSignals: [] })
  })

  it('starts with an empty signals list', () => {
    expect(useSignalsStore.getState().liveSignals).toHaveLength(0)
  })

  it('setSignals replaces all signals', () => {
    const signals = [makeSignal('a'), makeSignal('b')]
    useSignalsStore.getState().setSignals(signals)
    expect(useSignalsStore.getState().liveSignals).toHaveLength(2)
    expect(useSignalsStore.getState().liveSignals[0].id).toBe('a')
  })

  it('pushSignal prepends new signal to the front', () => {
    useSignalsStore.getState().setSignals([makeSignal('old')])
    useSignalsStore.getState().pushSignal(makeSignal('new'))
    const ids = useSignalsStore.getState().liveSignals.map((s) => s.id)
    expect(ids[0]).toBe('new')
    expect(ids[1]).toBe('old')
  })

  it('pushSignal caps list at 50 entries', () => {
    const initial = Array.from({ length: 50 }, (_, i) => makeSignal(`s${i}`))
    useSignalsStore.getState().setSignals(initial)
    useSignalsStore.getState().pushSignal(makeSignal('overflow'))
    expect(useSignalsStore.getState().liveSignals).toHaveLength(50)
    expect(useSignalsStore.getState().liveSignals[0].id).toBe('overflow')
  })

  it('setSignals with empty array clears the list', () => {
    useSignalsStore.getState().setSignals([makeSignal('x')])
    useSignalsStore.getState().setSignals([])
    expect(useSignalsStore.getState().liveSignals).toHaveLength(0)
  })
})
