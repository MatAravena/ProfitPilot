import { describe, it, expect } from 'vitest'
import { toSeriesData } from './chartSeries'

describe('toSeriesData', () => {
  it('converts ms timestamps to seconds and keeps close as value', () => {
    const out = toSeriesData([{ timestamp: 1_743_296_400_000, close: 42 }])
    expect(out).toEqual([{ time: 1_743_296_400, value: 42 }])
  })

  it('collapses duplicate timestamps, keeping the last value', () => {
    // The exact crash case: two consecutive points at the same second.
    const out = toSeriesData([
      { timestamp: 1_743_292_800_000, close: 100 },
      { timestamp: 1_743_296_400_000, close: 101 },
      { timestamp: 1_743_296_400_000, close: 105 }, // dup of prev second → last wins
    ])
    expect(out).toEqual([
      { time: 1_743_292_800, value: 100 },
      { time: 1_743_296_400, value: 105 },
    ])
  })

  it('sorts out-of-order input ascending by time', () => {
    const out = toSeriesData([
      { timestamp: 3_000, close: 3 },
      { timestamp: 1_000, close: 1 },
      { timestamp: 2_000, close: 2 },
    ])
    expect(out.map((p) => p.time)).toEqual([1, 2, 3])
  })

  it('is strictly ascending and unique for arbitrary input (setData contract)', () => {
    const out = toSeriesData([
      { timestamp: 1_000, close: 1 },
      { timestamp: 1_000, close: 9 },
      { timestamp: 5_000, close: 5 },
      { timestamp: 2_000, close: 2 },
      { timestamp: 5_000, close: 8 },
    ])
    for (let i = 1; i < out.length; i++) {
      expect(out[i].time as number).toBeGreaterThan(out[i - 1].time as number)
    }
  })

  it('returns empty for empty input', () => {
    expect(toSeriesData([])).toEqual([])
  })
})
