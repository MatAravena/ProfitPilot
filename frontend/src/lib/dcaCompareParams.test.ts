import { describe, it, expect, beforeEach } from 'vitest'
import {
  DEFAULT_DCA_PARAMS,
  DCA_FIELD_DEFS,
  DCA_PRESETS,
  mergeDcaParams,
  loadDcaParams,
  saveDcaParams,
  DCA_PARAMS_STORAGE_KEY,
} from './dcaCompareParams'

describe('DEFAULT_DCA_PARAMS', () => {
  it('mirrors the backend Field() defaults', () => {
    expect(DEFAULT_DCA_PARAMS.cycle.days_to_top).toBe(535)
    expect(DEFAULT_DCA_PARAMS.cycle.top_to_bottom).toBe(380)
    expect(DEFAULT_DCA_PARAMS.hunter.sell_cap_frac).toBe(0.3)
    expect(DEFAULT_DCA_PARAMS.rotation.sell_fraction_at_ath).toBe(0.7)
    expect(DEFAULT_DCA_PARAMS.rotation.caution_margin).toBe(0.05)
  })
})

describe('DCA_FIELD_DEFS', () => {
  it('has one field def per tunable key across all three blocks', () => {
    const keysPerGroup = (g: string) =>
      DCA_FIELD_DEFS.filter((f) => f.group === g).map((f) => f.key)
    expect(new Set(keysPerGroup('cycle'))).toEqual(new Set(Object.keys(DEFAULT_DCA_PARAMS.cycle)))
    expect(new Set(keysPerGroup('hunter'))).toEqual(new Set(Object.keys(DEFAULT_DCA_PARAMS.hunter)))
    expect(new Set(keysPerGroup('rotation'))).toEqual(new Set(Object.keys(DEFAULT_DCA_PARAMS.rotation)))
  })

  it('gives every numeric field a valid [min,max] range and positive step', () => {
    for (const f of DCA_FIELD_DEFS) {
      if (f.kind === 'enum') continue
      expect(f.min).toBeLessThan(f.max)
      expect(f.step).toBeGreaterThan(0)
    }
  })

  it('types the timing switch as an enum and the window bounds as nullable days', () => {
    const byKey = (k: string) => DCA_FIELD_DEFS.find((f) => f.key === k)!
    const mode = byKey('timing_mode')
    expect(mode.kind).toBe('enum')
    expect(mode.kind === 'enum' && mode.options).toEqual(['gaussian', 'windows'])
    for (const k of ['sell_start_day', 'sell_end_day', 'buy_start_day', 'buy_end_day']) {
      expect(byKey(k).kind).toBe('day')
    }
  })
})

describe('discrete halving windows', () => {
  it('defaults to the gaussian clock with auto-derived window bounds', () => {
    expect(DEFAULT_DCA_PARAMS.cycle.timing_mode).toBe('gaussian')
    expect(DEFAULT_DCA_PARAMS.cycle.sell_start_day).toBeNull()
    expect(DEFAULT_DCA_PARAMS.cycle.buy_end_day).toBeNull()
    expect(DEFAULT_DCA_PARAMS.cycle.ramp_days).toBe(0)
  })

  it('merges an explicit day offset and falls back to null for non-numbers', () => {
    expect(mergeDcaParams({ cycle: { sell_start_day: 500 } }).cycle.sell_start_day).toBe(500)
    expect(mergeDcaParams({ cycle: { sell_start_day: 'soon' } }).cycle.sell_start_day).toBeNull()
    expect(mergeDcaParams({ cycle: { sell_start_day: null } }).cycle.sell_start_day).toBeNull()
  })

  it('accepts a known timing mode and rejects an unknown one', () => {
    expect(mergeDcaParams({ cycle: { timing_mode: 'windows' } }).cycle.timing_mode).toBe('windows')
    expect(mergeDcaParams({ cycle: { timing_mode: 'vibes' } }).cycle.timing_mode).toBe('gaussian')
  })

  it('ships a windows preset with concrete buy/sell day offsets', () => {
    const p = DCA_PRESETS.halvingWindows
    expect(p.cycle.timing_mode).toBe('windows')
    expect(typeof p.cycle.sell_start_day).toBe('number')
    expect(p.cycle.sell_end_day!).toBeGreaterThan(p.cycle.sell_start_day!)
    expect(p.cycle.buy_start_day!).toBeGreaterThan(p.cycle.sell_end_day!)
  })
})

describe('mergeDcaParams', () => {
  it('fills missing fields from defaults, keeping supplied ones', () => {
    const merged = mergeDcaParams({ cycle: { days_to_top: 600 } })
    expect(merged.cycle.days_to_top).toBe(600)                       // supplied wins
    expect(merged.cycle.top_to_bottom).toBe(380)                     // missing -> default
    expect(merged.hunter).toEqual(DEFAULT_DCA_PARAMS.hunter)         // whole block default
  })

  it('returns defaults for null/garbage input', () => {
    expect(mergeDcaParams(null)).toEqual(DEFAULT_DCA_PARAMS)
    expect(mergeDcaParams({ nope: 1 })).toEqual(DEFAULT_DCA_PARAMS)
  })
})

describe('presets', () => {
  it('default preset equals the defaults', () => {
    expect(DCA_PRESETS.default).toEqual(DEFAULT_DCA_PARAMS)
  })

  it('sellEverything maxes the sell fractions', () => {
    expect(DCA_PRESETS.sellEverything.hunter.sell_cap_frac).toBe(1)
    expect(DCA_PRESETS.sellEverything.rotation.sell_fraction_at_ath).toBe(1)
  })
})

describe('persistence', () => {
  beforeEach(() => localStorage.clear())

  it('round-trips through localStorage', () => {
    const custom = mergeDcaParams({ rotation: { expected_bear_drop: 0.6 } })
    saveDcaParams(custom)
    expect(loadDcaParams().rotation.expected_bear_drop).toBe(0.6)
  })

  it('returns defaults when nothing is stored', () => {
    expect(loadDcaParams()).toEqual(DEFAULT_DCA_PARAMS)
  })

  it('returns defaults (not throw) when stored JSON is corrupt', () => {
    localStorage.setItem(DCA_PARAMS_STORAGE_KEY, '{not json')
    expect(loadDcaParams()).toEqual(DEFAULT_DCA_PARAMS)
  })
})
