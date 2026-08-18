// Single source of truth on the frontend for the DCA-compare tunable parameter blocks.
// Mirrors the backend Pydantic schemas (CycleParamsSchema / HunterParamsSchema /
// RotationParamsSchema in backend/app/models/schemas/backtest_schemas.py). Defaults, bounds,
// and steps live ONLY here so the tuning form derives inputs from one place.

/** How cycle position becomes behavior.
 *  - `gaussian`: smooth bell curves around the predicted top/bottom (sigma_* set their width).
 *  - `windows`:  discrete day windows — nothing before the start day, full intensity through the
 *    end day, nothing after ("start selling N days after the halving"). */
export type TimingMode = 'gaussian' | 'windows'

export const TIMING_MODES: readonly TimingMode[] = ['gaussian', 'windows']

export interface CycleParams {
  days_to_top: number
  top_to_bottom: number
  sigma_top: number
  sigma_bottom: number
  base_buy: number
  rolling_window: number
  k_buy: number
  k_sell: number
  timing_mode: TimingMode
  // Days since the most recent halving. null = derive from the gaussian params (top/bottom +/- sigma).
  sell_start_day: number | null
  sell_end_day: number | null
  buy_start_day: number | null
  buy_end_day: number | null
  ramp_days: number
}

export interface HunterParams {
  sell_cap_frac: number
  cooldown_days: number
  reentry_within: number
  k_bear_daily: number
}

export interface RotationParams {
  sell_fraction_at_ath: number
  ath_band: number
  sell_intensity_hi: number
  k_sell_daily: number
  sell_sharpness: number
  expected_bear_drop: number
  buy_zone_top_frac: number
  k_deploy_daily: number
  deploy_floor: number
  reentry_gain: number
  caution_margin: number
}

export interface DcaParams {
  cycle: CycleParams
  hunter: HunterParams
  rotation: RotationParams
}

export type DcaParamGroup = keyof DcaParams

export const DEFAULT_DCA_PARAMS: DcaParams = {
  cycle: {
    days_to_top: 535,
    top_to_bottom: 380,
    sigma_top: 90,
    sigma_bottom: 120,
    base_buy: 0.25,
    rolling_window: 90,
    k_buy: 0.5,
    k_sell: 0.35,
    timing_mode: 'gaussian',
    sell_start_day: null,
    sell_end_day: null,
    buy_start_day: null,
    buy_end_day: null,
    ramp_days: 0,
  },
  hunter: {
    sell_cap_frac: 0.3,
    cooldown_days: 90,
    reentry_within: 0.15,
    k_bear_daily: 0.05,
  },
  rotation: {
    sell_fraction_at_ath: 0.7,
    ath_band: 0.08,
    sell_intensity_hi: 0.85,
    k_sell_daily: 0.1,
    sell_sharpness: 4.0,
    expected_bear_drop: 0.7,
    buy_zone_top_frac: 0.5,
    k_deploy_daily: 0.1,
    deploy_floor: 0.3,
    reentry_gain: 0.3,
    caution_margin: 0.05,
  },
}

/** `number` = required numeric input · `day` = nullable day-offset (empty means "auto-derive")
 *  · `enum` = fixed choice. The kind drives BOTH how the field renders and how merge validates it. */
export type FieldDef =
  | { group: DcaParamGroup; key: string; kind?: 'number'; min: number; max: number; step: number }
  | { group: DcaParamGroup; key: string; kind: 'day'; min: number; max: number; step: number }
  | { group: DcaParamGroup; key: string; kind: 'enum'; options: readonly string[] }

// Bounds mirror the backend Field(ge=..., le=...) constraints; step is a sensible UI granularity.
export const DCA_FIELD_DEFS: FieldDef[] = [
  { group: 'cycle', key: 'timing_mode', kind: 'enum', options: TIMING_MODES },
  { group: 'cycle', key: 'sell_start_day', kind: 'day', min: 0, max: 1457, step: 5 },
  { group: 'cycle', key: 'sell_end_day', kind: 'day', min: 0, max: 1457, step: 5 },
  { group: 'cycle', key: 'buy_start_day', kind: 'day', min: 0, max: 1457, step: 5 },
  { group: 'cycle', key: 'buy_end_day', kind: 'day', min: 0, max: 1457, step: 5 },
  { group: 'cycle', key: 'ramp_days', kind: 'number', min: 0, max: 200, step: 1 },
  { group: 'cycle', key: 'days_to_top', min: 200, max: 900, step: 5 },
  { group: 'cycle', key: 'top_to_bottom', min: 200, max: 900, step: 5 },
  { group: 'cycle', key: 'sigma_top', min: 1, max: 400, step: 5 },
  { group: 'cycle', key: 'sigma_bottom', min: 1, max: 400, step: 5 },
  { group: 'cycle', key: 'base_buy', min: 0, max: 1, step: 0.05 },
  { group: 'cycle', key: 'rolling_window', min: 7, max: 400, step: 1 },
  { group: 'cycle', key: 'k_buy', min: 0.05, max: 1, step: 0.05 },
  { group: 'cycle', key: 'k_sell', min: 0.05, max: 1, step: 0.05 },

  { group: 'hunter', key: 'sell_cap_frac', min: 0, max: 1, step: 0.05 },
  { group: 'hunter', key: 'cooldown_days', min: 0, max: 365, step: 1 },
  { group: 'hunter', key: 'reentry_within', min: 0, max: 1, step: 0.05 },
  { group: 'hunter', key: 'k_bear_daily', min: 0.01, max: 1, step: 0.01 },

  { group: 'rotation', key: 'sell_fraction_at_ath', min: 0, max: 1, step: 0.05 },
  { group: 'rotation', key: 'ath_band', min: 0.01, max: 0.5, step: 0.01 },
  { group: 'rotation', key: 'sell_intensity_hi', min: 0, max: 1, step: 0.05 },
  { group: 'rotation', key: 'k_sell_daily', min: 0.01, max: 1, step: 0.01 },
  { group: 'rotation', key: 'sell_sharpness', min: 1, max: 12, step: 0.5 },
  { group: 'rotation', key: 'expected_bear_drop', min: 0.05, max: 0.95, step: 0.05 },
  { group: 'rotation', key: 'buy_zone_top_frac', min: 0, max: 1, step: 0.05 },
  { group: 'rotation', key: 'k_deploy_daily', min: 0.01, max: 1, step: 0.01 },
  { group: 'rotation', key: 'deploy_floor', min: 0, max: 1, step: 0.05 },
  { group: 'rotation', key: 'reentry_gain', min: 0.05, max: 2, step: 0.05 },
  { group: 'rotation', key: 'caution_margin', min: 0, max: 0.5, step: 0.01 },
]

// Declared before the presets below, which merge through it at module-init time.
const FIELD_DEF_BY_PATH = new Map(DCA_FIELD_DEFS.map((f) => [`${f.group}.${f.key}`, f]))

// Named presets. `default` must equal DEFAULT_DCA_PARAMS; the rest are meaningful starting points
// documented in the README/tests (keep-core vs sell-everything vs aggressive dip buying).
export const DCA_PRESETS: Record<string, DcaParams> = {
  default: DEFAULT_DCA_PARAMS,
  keepCore: mergeInto({
    hunter: { sell_cap_frac: 0.2 },
    rotation: { sell_fraction_at_ath: 0.5, buy_zone_top_frac: 0.5 },
  }),
  sellEverything: mergeInto({
    hunter: { sell_cap_frac: 1 },
    rotation: { sell_fraction_at_ath: 1, expected_bear_drop: 0.7 },
  }),
  aggressiveDip: mergeInto({
    cycle: { base_buy: 0.4, k_buy: 1, rolling_window: 60 },
    rotation: { buy_zone_top_frac: 0.75, k_deploy_daily: 0.2, deploy_floor: 0.4 },
  }),
  // Discrete halving windows: sell across the predicted top (day 445-625 after the halving), buy
  // across the predicted bottom (day 795-1035) — i.e. the gaussian mass turned into hard dates.
  halvingWindows: mergeInto({
    cycle: {
      timing_mode: 'windows',
      sell_start_day: 445,
      sell_end_day: 625,
      buy_start_day: 795,
      buy_end_day: 1035,
    },
  }),
}

export const DCA_PRESET_IDS = Object.keys(DCA_PRESETS)

export const DCA_PARAMS_STORAGE_KEY = 'profitpilot.dcaCompareParams'

/** Deep-merge a partial (from a preset literal) over the defaults. */
function mergeInto(partial: DeepPartial<DcaParams>): DcaParams {
  return mergeDcaParams(partial)
}

type DeepPartial<T> = { [K in keyof T]?: Partial<T[K]> }

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

/** Accept `v` for one field, or fall back to its default. The field's kind decides what's valid,
 *  so validation can never drift from what the form renders. */
function coerceField(def: FieldDef | undefined, v: unknown, fallback: unknown): unknown {
  if (def?.kind === 'enum') return typeof v === 'string' && def.options.includes(v) ? v : fallback
  if (def?.kind === 'day') {
    if (v === null) return null
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback
  }
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

/** Merge arbitrary/untrusted input (persisted or partial) over the defaults, block by block.
 *  Unknown keys are ignored; invalid values fall back; missing blocks/fields fall back. */
export function mergeDcaParams(input: unknown): DcaParams {
  const src = isRecord(input) ? input : {}
  const out = {} as DcaParams
  for (const group of Object.keys(DEFAULT_DCA_PARAMS) as DcaParamGroup[]) {
    const defBlock = DEFAULT_DCA_PARAMS[group] as Record<string, unknown>
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

export function saveDcaParams(params: DcaParams): void {
  try {
    localStorage.setItem(DCA_PARAMS_STORAGE_KEY, JSON.stringify(params))
  } catch {
    // storage unavailable / quota — non-fatal, tuning just won't persist this session.
  }
}

export function loadDcaParams(): DcaParams {
  try {
    const raw = localStorage.getItem(DCA_PARAMS_STORAGE_KEY)
    if (!raw) return DEFAULT_DCA_PARAMS
    return mergeDcaParams(JSON.parse(raw))
  } catch {
    return DEFAULT_DCA_PARAMS
  }
}
