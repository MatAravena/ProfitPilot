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
