import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  DEFAULT_GRID_PARAMS,
  GRID_FIELD_DEFS,
  GRID_PARAMS_STORAGE_KEY,
  GRID_PRESETS,
  GRID_PRESET_IDS,
  loadGridParams,
  mergeGridParams,
  saveGridParams,
} from './gridParams'

describe('gridParams', () => {
  it('every field def maps to a key present in the defaults', () => {
    for (const f of GRID_FIELD_DEFS) {
      const block = DEFAULT_GRID_PARAMS[f.group] as unknown as Record<string, unknown>
      expect(block).toHaveProperty(f.key)
    }
  })

  it('mergeGridParams falls back to defaults for garbage input', () => {
    const merged = mergeGridParams({ grid: { min_edge: 'not-a-number' }, garbage: true })
    expect(merged.grid.min_edge).toBe(DEFAULT_GRID_PARAMS.grid.min_edge)
  })

  it('mergeGridParams accepts a valid partial override', () => {
    const merged = mergeGridParams({ grid: { min_edge: 5 } })
    expect(merged.grid.min_edge).toBe(5)
    expect(merged.regime.ema_fast).toBe(DEFAULT_GRID_PARAMS.regime.ema_fast)
  })

  it('mergeGridParams validates the spacing_mode enum', () => {
    const merged = mergeGridParams({ grid: { spacing_mode: 'not-a-mode' } })
    expect(merged.grid.spacing_mode).toBe(DEFAULT_GRID_PARAMS.grid.spacing_mode)
  })

  it('every named preset is a fully valid GridTuningParams', () => {
    for (const id of GRID_PRESET_IDS) {
      const preset = GRID_PRESETS[id]
      expect(mergeGridParams(preset)).toEqual(preset)
    }
  })

  describe('localStorage persistence', () => {
    beforeEach(() => {
      const store: Record<string, string> = {}
      vi.stubGlobal('localStorage', {
        getItem: (k: string) => store[k] ?? null,
        setItem: (k: string, v: string) => { store[k] = v },
        removeItem: (k: string) => { delete store[k] },
      })
    })

    it('loadGridParams returns defaults when nothing is stored', () => {
      expect(loadGridParams()).toEqual(DEFAULT_GRID_PARAMS)
    })

    it('saveGridParams then loadGridParams round-trips', () => {
      const custom = mergeGridParams({ grid: { min_edge: 7 } })
      saveGridParams(custom)
      expect(loadGridParams().grid.min_edge).toBe(7)
      expect(localStorage.getItem(GRID_PARAMS_STORAGE_KEY)).toBeTruthy()
    })
  })
})
