// Mirrors backend backtest_schemas.py + broker_schemas.py

export interface BacktestRequest {
  strategy_name: string
  symbol: string
  timeframe: string
  start?: string
  end?: string
  initial_capital: number
  commission_pct: number
  slippage_pct?: number   // adverse slippage per fill (spread + impact); default 5 bps
  stop_loss_pct?: number | null
  take_profit_pct?: number | null
  position_size_pct?: number | null   // fraction of equity per entry (same model as live); null → backend 2% default
  risk_per_trade_pct?: number | null  // risk mode: size = risk / stop, capped at position_size_pct; needs a stop
  parameters: Record<string, unknown>
}

export interface BacktestMetrics {
  total_return_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate: number
  profit_factor: number | null   // null = no losing trades (rendered as "∞")
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_win: number
  avg_loss: number
  final_equity: number
}

export interface EquityPoint {
  timestamp: number  // Unix ms
  value: number
}

export interface PricePoint {
  timestamp: number  // Unix ms
  close: number
}

export interface TradeRecord {
  symbol: string
  side: string
  entry_price: number
  exit_price: number
  size: number
  pnl: number
  pnl_pct: number
  entry_time: number  // Unix ms
  exit_time: number   // Unix ms
}

export interface BacktestResponse {
  strategy_name: string
  symbol: string
  timeframe: string
  initial_capital: number
  metrics: BacktestMetrics
  equity_curve: EquityPoint[]
  trades: TradeRecord[]
  prices: PricePoint[]
}

export interface MonteCarloRequest extends BacktestRequest {
  n_simulations?: number
  methods?: MonteCarloMethod[]
  seed?: number | null
}

export type MonteCarloMethod = 'bootstrap' | 'shuffle'

// --- DCA vs halving-cycle-grid comparison (mirrors backend DcaCompareResponse) ---

import type { CycleParams, HunterParams, RotationParams } from '@/lib/dcaCompareParams'

export interface DcaCompareRequest {
  symbol: string
  timeframe: string
  start?: string
  end?: string
  capital_model: 'contributions' | 'lump_sum'
  contribution_amount: number
  contribution_interval_days: number
  lump_sum_budget?: number
  commission_pct?: number
  slippage_pct?: number
  // Optional per-arm tuning blocks (backend applies defaults when omitted).
  cycle?: CycleParams
  hunter?: HunterParams
  rotation?: RotationParams
}

export interface DcaArmResult {
  equity_curve: EquityPoint[]
  final_value: number
  total_contributed: number
  total_return_pct: number
  units_accumulated: number
  avg_cost_basis: number
  max_drawdown_pct: number
  sharpe_ratio: number
  dry_powder: number
  realized_pnl: number
}

export interface CycleMarker {
  timestamp: number   // Unix ms
  kind: 'top' | 'bottom'
}

export interface DcaCompareResponse {
  symbol: string
  timeframe: string
  capital_model: string
  caveat: string
  cycle_markers: CycleMarker[]
  arms: Record<string, DcaArmResult>
}

export interface PercentileStats {
  p5: number
  p25: number
  p50: number
  p75: number
  p95: number
  min: number
  max: number
  mean: number
}

export interface MonteCarloHistogram {
  edges: number[]   // length === counts.length + 1
  counts: number[]
}

export interface MonteCarloMethodResult {
  method: string
  final_equity: PercentileStats
  total_return_pct: PercentileStats
  max_drawdown_pct: PercentileStats
  prob_profit: number                  // fraction of sims ending above initial capital
  risk_of_exceeding_drawdown: number   // fraction whose max-drawdown exceeds the threshold
  risk_of_ruin: number                 // fraction that hit equity <= 0
  histogram: MonteCarloHistogram
}

export interface MonteCarloResponse {
  strategy_name: string
  symbol: string
  timeframe: string
  initial_capital: number
  n_simulations: number
  n_trades: number
  realized_total_return_pct: number   // the single-path backtest result, for reference lines
  drawdown_threshold_pct: number
  methods: Record<string, MonteCarloMethodResult>
}

export interface StrategyParamDef {
  key: string
  type: 'int' | 'float' | string
  default: number
  label: string
  description?: string
}

export interface StrategyMeta {
  class_name: string
  display_name: string
  description: string
  parameters: StrategyParamDef[]
}

export interface AvailableStrategiesResponse {
  strategies: StrategyMeta[]
}

// Mirrors backend walk_forward_schemas.py
export interface WalkForwardRequest extends BacktestRequest {
  param_grid: Record<string, number[]>
  train_days: number
  test_days: number
  objective?: 'sharpe_ratio' | 'total_return_pct' | 'profit_factor' | 'win_rate'
}

export interface WalkForwardFold {
  train_start: number   // Unix ms
  train_end: number
  test_start: number
  test_end: number
  params: Record<string, number | string | boolean>
  is_score: number
  is_return_pct: number
  oos_return_pct: number
  oos_sharpe: number
  oos_max_drawdown_pct: number
  oos_trades: number
  buy_hold_return_pct: number
}

export interface WalkForwardResponse {
  strategy_name: string
  symbol: string
  timeframe: string
  objective: string
  initial_capital: number
  train_bars: number
  test_bars: number
  combinations: number
  skipped_combinations: number
  oos_total_return_pct: number
  oos_max_drawdown_pct: number
  oos_sharpe: number
  buy_hold_total_return_pct: number
  buy_hold_max_drawdown_pct: number
  pct_folds_profitable: number
  avg_is_score: number
  avg_oos_sharpe: number
  distinct_param_sets: number
  folds: WalkForwardFold[]
  equity_curve: EquityPoint[]
  buy_hold_curve: EquityPoint[]
  caveat: string
}

// Mirrors PortfolioSummaryResponse from backend
export interface AccountSummary {
  broker_id: string
  account_id: string
  equity: number
  cash: number
  buying_power: number
  paper_mode: boolean
  currency: string
  updated_at: string
}

export interface PortfolioSummary {
  total_equity: number
  total_cash: number
  total_unrealized_pnl: number
  positions: PortfolioPosition[]
  accounts: AccountSummary[]
}

export interface PortfolioPosition {
  symbol: string
  market_type: string
  broker_id: string
  quantity: number
  avg_entry_price: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  opened_at: string
}

// --- Grid bot (mirrors backend GridResponse in app/models/schemas/grid_schemas.py) ---

import type { GridBlockParams, RegimeBlockParams } from '@/lib/gridParams'

export interface GridArmResult {
  equity_curve: EquityPoint[]
  final_equity: number
  total_return_pct: number
  max_drawdown_pct: number
  sharpe_ratio: number
  grid_trades: number
  /** Realized P&L from matched rung pairs — the actual grid income. */
  grid_realized_pnl: number
  /** P&L from guard-triggered forced exits — NOT grid income, and not mark-to-market drift
   *  either. Reported separately so grid_realized_pnl + forced_exit_pnl + mark_to_market_pnl
   *  actually reconciles to total_return_pct. */
  forced_exit_pnl: number
  /** How many times a policy's guard fired a full forced close (e.g. GuardedReanchorPolicy's
   *  reanchor exit). The guarded arm's headline risk stat. */
  force_close_count: number
  /** Everything else: unrealized drift on inventory still held. Kept separate on purpose. */
  mark_to_market_pnl: number
  avg_profit_per_grid_pct: number
  fill_rate: number
  time_in_grid_pct: number
  max_inventory_notional: number
  worst_unrealized_pct: number
  time_underwater_pct: number
}

export interface GridResponse {
  symbol: string
  timeframe: string
  allow_intrabar_roundtrip: boolean
  /** SHORT_BIASED legs omit perp funding cost — disclosed, not fixed, in v1. */
  funding_rate_caveat: string
  arms: Record<string, GridArmResult>
}

export interface GridRequest {
  symbol: string
  timeframe: string
  start?: string
  end?: string
  initial_capital?: number
  notional_per_rung?: number
  allow_intrabar_roundtrip?: boolean
  grid?: GridBlockParams
  regime?: RegimeBlockParams
}
