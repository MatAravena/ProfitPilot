// Single source of truth on the frontend for the grid-bot tunable parameter blocks. Mirrors the
// backend Pydantic schemas (GridParamsSchema / RegimeParamsSchema in
// backend/app/models/schemas/grid_schemas.py) and the dcaCompareParams.ts pattern.

export type SpacingMode = 'geometric' | 'arithmetic'
export const SPACING_MODES: readonly SpacingMode[] = ['geometric', 'arithmetic']

export interface GridBlockParams {
  range_atr_mult: number
  spacing_mode: SpacingMode
  spacing_atr_mult: number
  min_edge: number
  min_rungs: number
  max_rungs: number
  fee_pct: number
  slippage_pct: number
  max_extensions: number
  reanchor_buffer_pct: number
  cooldown_bars: number
}

export interface RegimeBlockParams {
  ema_fast: number
  ema_mid: number
  ema_slow: number
  atr_period: number
  atr_vol_low: number
  atr_vol_high: number
  bb_period: number
  bb_std: number
  squeeze_pctile: number
  atr_pctile_window: number
  bandwidth_pctile_window: number
  swing_confirm_bars: number
  supertrend_period: number
  supertrend_mult: number
}

export interface GridTuningParams {
  grid: GridBlockParams
  regime: RegimeBlockParams
}

export type GridParamGroup = keyof GridTuningParams

export const DEFAULT_GRID_PARAMS: GridTuningParams = {
  grid: {
    range_atr_mult: 3.0, spacing_mode: 'geometric', spacing_atr_mult: 0.30, min_edge: 3.0,
    min_rungs: 8, max_rungs: 30, fee_pct: 0.001, slippage_pct: 0.0005, max_extensions: 3,
    reanchor_buffer_pct: 0.01, cooldown_bars: 5,
  },
  regime: {
    ema_fast: 9, ema_mid: 20, ema_slow: 50, atr_period: 14, atr_vol_low: 0.35, atr_vol_high: 0.90,
    bb_period: 20, bb_std: 2.0, squeeze_pctile: 0.20, atr_pctile_window: 200,
    bandwidth_pctile_window: 200, swing_confirm_bars: 3, supertrend_period: 10, supertrend_mult: 3.0,
  },
}

export type FieldDef =
  | { group: GridParamGroup; key: string; kind?: 'number'; min: number; max: number; step: number }
  | { group: GridParamGroup; key: string; kind: 'enum'; options: readonly string[] }

export const GRID_FIELD_DEFS: FieldDef[] = [
  { group: 'grid', key: 'spacing_mode', kind: 'enum', options: SPACING_MODES },
  { group: 'grid', key: 'range_atr_mult', min: 0.5, max: 10, step: 0.1 },
  { group: 'grid', key: 'spacing_atr_mult', min: 0.01, max: 5, step: 0.01 },
  { group: 'grid', key: 'min_edge', min: 0.5, max: 20, step: 0.5 },
  { group: 'grid', key: 'min_rungs', min: 2, max: 100, step: 1 },
  { group: 'grid', key: 'max_rungs', min: 2, max: 100, step: 1 },
  { group: 'grid', key: 'fee_pct', min: 0, max: 0.05, step: 0.0001 },
  { group: 'grid', key: 'slippage_pct', min: 0, max: 0.05, step: 0.0001 },
  { group: 'grid', key: 'max_extensions', min: 0, max: 10, step: 1 },
  { group: 'grid', key: 'reanchor_buffer_pct', min: 0, max: 0.5, step: 0.005 },
  { group: 'grid', key: 'cooldown_bars', min: 0, max: 500, step: 1 },

  { group: 'regime', key: 'ema_fast', min: 2, max: 200, step: 1 },
  { group: 'regime', key: 'ema_mid', min: 2, max: 400, step: 1 },
  { group: 'regime', key: 'ema_slow', min: 2, max: 800, step: 1 },
  { group: 'regime', key: 'atr_period', min: 2, max: 200, step: 1 },
  { group: 'regime', key: 'atr_vol_low', min: 0, max: 1, step: 0.05 },
  { group: 'regime', key: 'atr_vol_high', min: 0, max: 1, step: 0.05 },
  { group: 'regime', key: 'bb_period', min: 2, max: 200, step: 1 },
  { group: 'regime', key: 'bb_std', min: 0.5, max: 5, step: 0.1 },
  { group: 'regime', key: 'squeeze_pctile', min: 0, max: 1, step: 0.05 },
  { group: 'regime', key: 'atr_pctile_window', min: 10, max: 2000, step: 10 },
  { group: 'regime', key: 'bandwidth_pctile_window', min: 10, max: 2000, step: 10 },
  { group: 'regime', key: 'swing_confirm_bars', min: 1, max: 50, step: 1 },
  { group: 'regime', key: 'supertrend_period', min: 2, max: 100, step: 1 },
  { group: 'regime', key: 'supertrend_mult', min: 0.5, max: 10, step: 0.1 },
]

const FIELD_DEF_BY_PATH = new Map(GRID_FIELD_DEFS.map((f) => [`${f.group}.${f.key}`, f]))

export const GRID_PARAMS_STORAGE_KEY = 'profitpilot.gridParams'

type DeepPartial<T> = { [K in keyof T]?: Partial<T[K]> }

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

function coerceField(def: FieldDef | undefined, v: unknown, fallback: unknown): unknown {
  if (def?.kind === 'enum') return typeof v === 'string' && def.options.includes(v) ? v : fallback
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

/** Merge arbitrary/untrusted input (persisted or partial) over the defaults, block by block.
 *  Unknown keys are ignored; invalid values fall back; missing blocks/fields fall back. */
export function mergeGridParams(input: unknown): GridTuningParams {
  const src = isRecord(input) ? input : {}
  const out = {} as GridTuningParams
  for (const group of Object.keys(DEFAULT_GRID_PARAMS) as GridParamGroup[]) {
    const defBlock = DEFAULT_GRID_PARAMS[group] as unknown as Record<string, unknown>
    const srcBlock = isRecord(src[group]) ? (src[group] as Record<string, unknown>) : {}
    const merged: Record<string, unknown> = {}
    for (const key of Object.keys(defBlock)) {
      const def = FIELD_DEF_BY_PATH.get(`${group}.${key}`)
      merged[key] = coerceField(def, srcBlock[key], defBlock[key])
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(out as any)[group] = merged
  }
  return out
}

function mergeInto(partial: DeepPartial<GridTuningParams>): GridTuningParams {
  return mergeGridParams(partial)
}

// `default` must equal DEFAULT_GRID_PARAMS; the rest are meaningful starting points.
export const GRID_PRESETS: Record<string, GridTuningParams> = {
  default: DEFAULT_GRID_PARAMS,
  tight: mergeInto({ grid: { spacing_atr_mult: 0.15, min_edge: 1.5, range_atr_mult: 2.0 } }),
  wide: mergeInto({ grid: { spacing_atr_mult: 0.5, min_edge: 4.0, range_atr_mult: 4.0 } }),
}

export const GRID_PRESET_IDS = Object.keys(GRID_PRESETS)

export function saveGridParams(params: GridTuningParams): void {
  try {
    localStorage.setItem(GRID_PARAMS_STORAGE_KEY, JSON.stringify(params))
  } catch {
    // storage unavailable / quota — non-fatal, tuning just won't persist this session.
  }
}

export function loadGridParams(): GridTuningParams {
  try {
    const raw = localStorage.getItem(GRID_PARAMS_STORAGE_KEY)
    if (!raw) return DEFAULT_GRID_PARAMS
    return mergeGridParams(JSON.parse(raw))
  } catch {
    return DEFAULT_GRID_PARAMS
  }
}
