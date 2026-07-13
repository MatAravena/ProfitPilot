// Core domain types — mirrors backend/app/core/types.py

export type Direction = 'long' | 'short'
export type OrderStatus = 'pending' | 'open' | 'filled' | 'cancelled' | 'rejected'
export type StrategyLifecycle = 'draft' | 'paper' | 'live' | 'halted'
export type MarketType = 'spot' | 'futures' | 'options'
export type BrokerName = 'alpaca' | 'bybit' | 'binance'

export interface OHLCVCandle {
  time: number     // Unix timestamp (seconds)
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Position {
  id: string
  symbol: string
  direction: Direction
  size: number
  entryPrice: number
  currentPrice: number
  unrealizedPnl: number
  unrealizedPnlPct: number
  marketType: MarketType
  broker: BrokerName
  openedAt: string
}

export interface Fill {
  id: string
  orderId: string
  symbol: string
  direction: Direction
  size: number
  price: number
  fee: number
  filledAt: string
}

export interface Order {
  id: string
  symbol: string
  direction: Direction
  size: number
  price: number | null
  status: OrderStatus
  strategyId: string | null
  broker: BrokerName
  fills: Fill[]
  createdAt: string
  updatedAt: string
}

export interface Strategy {
  id: string
  name: string
  description: string
  status: StrategyLifecycle
  broker: BrokerName
  symbols: string[]
  lastSignalAt: string | null
  totalPnl: number
  winRate: number
  createdAt: string
}

export interface StrategyStatusUpdate {
  id: string
  status: StrategyLifecycle
  lastSignalAt: string | null
}

export interface BrokerAccount {
  broker: BrokerName
  equity: number
  cashBalance: number
  buyingPower: number
  isPaperMode: boolean
  isConnected: boolean
}

export interface PortfolioSnapshot {
  equity: number
  cashBalance: number
  dailyPnl: number
  totalPnl: number
  drawdown: number
  positions: Position[]
  updatedAt: number
}

// WebSocket message envelope
export interface WSMessage {
  channel: string
  data: unknown
}

// Broker connection (mirrors BrokerConnectionResponse)
export interface BrokerConnection {
  id: string
  broker_id: BrokerName
  label: string
  is_paper: boolean
  is_active: boolean
  created_at: string
}

export interface ConnectBrokerPayload {
  broker_id: BrokerName
  api_key: string
  secret_key: string
  label: string
  is_paper: boolean
}

// Strategy instance (mirrors StrategyInstanceResponse from backend)
export type StrategyStatus = 'draft' | 'paper' | 'live' | 'paused' | 'archived' | 'halted'

// Per-user risk defaults (mirrors backend RiskProfileSchema). All _pct fields are fractions.
export interface RiskProfile {
  stop_loss_pct: number
  take_profit_pct: number | null
  max_open_positions: number
  max_daily_drawdown_pct: number
  max_total_drawdown_pct: number
  max_orders_per_minute: number
  kill_switch_enabled: boolean
}

// Per-strategy config (mirrors backend ExecutionConfig). Behavioral fields are always set;
// risk fields are optional overrides — null ⇒ inherit the user's RiskProfile.
export interface ExecutionConfig {
  size_pct: number
  allow_short: boolean
  poll_seconds: number | null
  stop_loss_pct: number | null
  take_profit_pct: number | null
  max_open_positions: number | null
  max_daily_drawdown_pct: number | null
  max_total_drawdown_pct: number | null
  max_orders_per_minute: number | null
  kill_switch_enabled: boolean | null
}

export interface StrategyInstance {
  id: string
  class_name: string
  label: string
  symbol: string
  timeframe: string
  broker_connection_id: string | null
  status: StrategyStatus
  parameters: Record<string, number | string | boolean>
  execution: ExecutionConfig
  created_at: string
  updated_at: string
  last_signal_at: string | null
  error_count: number
}

export interface StrategyClassDef {
  class_name: string
  display_name: string
  description: string
  parameters: Array<{
    key: string
    type: 'int' | 'float' | 'string' | 'bool'
    default: number | string | boolean
    label: string
  }>
}

// Signal from a running strategy
export interface SignalRecord {
  id: string
  strategy_instance_id: string
  symbol: string
  timeframe: string
  direction: 'long' | 'short' | 'close' | 'neutral'
  confidence: number
  source: string
  generated_at: string
  close_price: number | null
}

// One row from order_records — an order attempt by the executor.
export interface OrderRecord {
  id: string
  symbol: string
  side: 'buy' | 'sell' | null
  quantity: number | null
  status: string
  reason: string | null
  avg_price: number | null
  filled_qty: number | null
  realized_pnl: number | null
  signal_id: string | null
  created_at: string
}

// Portfolio equity snapshot
export interface PortfolioSnapshotPoint {
  snapped_at: string
  equity: number
  cash: number
  unrealized_pnl: number
}

export interface CreateStrategyPayload {
  class_name: string
  label: string
  symbol: string
  timeframe: string
  broker_connection_id: string | null
  parameters: Record<string, number | string | boolean>
  execution?: ExecutionConfig
}

export interface PlaceOrderPayload {
  symbol: string
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  quantity: number
  limit_price?: number
  time_in_force?: 'day' | 'gtc' | 'ioc' | 'fok'
}

export interface OrderResult {
  order_id: string
  broker_order_id: string
  status: string
  submitted_at: string
}
