// Central registry of indicators: drives the controls panel (toggles + param
// inputs) and the TradingChart renderer. Each indicator declares its kind
// (overlay on the price scale vs. its own pane) and adjustable parameters.

export type IndicatorId =
  | 'sma' | 'ema' | 'wma' | 'bollinger' | 'vwap' | 'psar'   // overlays
  | 'volume' | 'rsi' | 'macd' | 'stochastic' | 'atr'        // panes

export type IndicatorKind = 'overlay' | 'pane'

export interface ParamDef {
  key: string
  label: string
  default: number
  min: number
  max: number
  step: number
}

export interface IndicatorDef {
  id: IndicatorId
  label: string
  kind: IndicatorKind
  color: string
  params: ParamDef[]
}

const p = (key: string, label: string, def: number, min: number, max: number, step = 1): ParamDef =>
  ({ key, label, default: def, min, max, step })

export const INDICATORS: IndicatorDef[] = [
  // ── Overlays ──
  { id: 'sma', label: 'SMA', kind: 'overlay', color: '#f59e0b', params: [p('period', 'Period', 20, 2, 400)] },
  { id: 'ema', label: 'EMA', kind: 'overlay', color: '#8b5cf6', params: [p('period', 'Period', 50, 2, 400)] },
  { id: 'wma', label: 'WMA', kind: 'overlay', color: '#ec4899', params: [p('period', 'Period', 20, 2, 400)] },
  {
    id: 'bollinger', label: 'Bollinger Bands', kind: 'overlay', color: '#38bdf8',
    params: [p('period', 'Period', 20, 2, 200), p('stdDev', 'Std Dev', 2, 0.5, 5, 0.1)],
  },
  { id: 'vwap', label: 'VWAP', kind: 'overlay', color: '#14b8a6', params: [] },
  {
    id: 'psar', label: 'Parabolic SAR', kind: 'overlay', color: '#a3e635',
    params: [p('step', 'Step', 0.02, 0.005, 0.2, 0.005), p('max', 'Max', 0.2, 0.05, 0.5, 0.05)],
  },
  // ── Panes ──
  { id: 'volume', label: 'Volume', kind: 'pane', color: '#64748b', params: [] },
  { id: 'rsi', label: 'RSI', kind: 'pane', color: '#22d3ee', params: [p('period', 'Period', 14, 2, 100)] },
  {
    id: 'macd', label: 'MACD', kind: 'pane', color: '#2563eb',
    params: [p('fast', 'Fast', 12, 2, 100), p('slow', 'Slow', 26, 3, 200), p('signal', 'Signal', 9, 2, 100)],
  },
  {
    id: 'stochastic', label: 'Stochastic', kind: 'pane', color: '#f97316',
    params: [p('k', '%K', 14, 2, 100), p('d', '%D', 3, 1, 50), p('smooth', 'Smooth', 3, 1, 50)],
  },
  { id: 'atr', label: 'ATR', kind: 'pane', color: '#eab308', params: [p('period', 'Period', 14, 2, 100)] },
]

export const INDICATOR_MAP: Record<IndicatorId, IndicatorDef> =
  Object.fromEntries(INDICATORS.map((d) => [d.id, d])) as Record<IndicatorId, IndicatorDef>

export interface IndicatorState {
  enabled: boolean
  params: Record<string, number>
}

export type IndicatorSettings = Record<IndicatorId, IndicatorState>

/** Build the default settings: a sensible starter set enabled, the rest off. */
export function defaultIndicatorSettings(): IndicatorSettings {
  const enabledByDefault: IndicatorId[] = ['volume', 'sma', 'ema', 'rsi']
  const settings = {} as IndicatorSettings
  for (const def of INDICATORS) {
    const params: Record<string, number> = {}
    for (const pd of def.params) params[pd.key] = pd.default
    settings[def.id] = { enabled: enabledByDefault.includes(def.id), params }
  }
  return settings
}
