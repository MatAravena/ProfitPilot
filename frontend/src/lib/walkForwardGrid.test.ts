import { describe, it, expect } from 'vitest'
import { buildParamGrid, gridSize } from './walkForwardGrid'
import type { StrategyParamDef } from '@/types/backtest'

const defs: StrategyParamDef[] = [
  { key: 'fast_period', type: 'int', default: 12, label: 'Fast' },
  { key: 'slow_period', type: 'int', default: 26, label: 'Slow' },
  { key: 'std_mult', type: 'float', default: 2, label: 'Std' },
]

describe('buildParamGrid', () => {
  it('searches half, same and 1.5x the current values', () => {
    expect(buildParamGrid(defs, { fast_period: 16, slow_period: 21, std_mult: 2 })).toEqual({
      fast_period: [8, 16, 24],
      slow_period: [11, 21, 32],
      std_mult: [1, 2, 3],
    })
  })

  it('falls back to defaults and keeps integer periods >= 2 without duplicates', () => {
    const grid = buildParamGrid([{ key: 'rsi_period', type: 'int', default: 2, label: 'RSI' }], {})
    expect(grid).toEqual({ rsi_period: [2, 3] })
  })

  it('skips non-numeric values', () => {
    expect(buildParamGrid(defs.slice(0, 1), { fast_period: 'abc' })).toEqual({})
  })

  it('counts combinations', () => {
    expect(gridSize({ a: [1, 2, 3], b: [1, 2] })).toBe(6)
    expect(gridSize({})).toBe(1)
  })
})
