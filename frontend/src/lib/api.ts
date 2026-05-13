import type {
  Order,
  OrderResult,
  PlaceOrderPayload,
  Position,
  OHLCVCandle,
  BrokerConnection,
  ConnectBrokerPayload,
  StrategyInstance,
  StrategyClassDef,
  CreateStrategyPayload,
  SignalRecord,
  PortfolioSnapshotPoint,
} from '@/types'
import type {
  BacktestRequest,
  BacktestResponse,
  PortfolioSummary,
  AvailableStrategiesResponse,
} from '@/types/backtest'

const BASE_URL = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const error = await res.text()
    throw new Error(error || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: {
    check: () => request<{ status: string }>('/health'),
  },

  market: {
    ohlcv: (symbol: string, timeframe: string, limit = 500, source?: 'bybit' | 'yfinance') =>
      request<OHLCVCandle[]>(
        `/market/ohlcv?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}${source ? `&source=${source}` : ''}`
      ),
  },

  portfolio: {
    summary: () => request<PortfolioSummary>('/portfolio/summary'),
    positions: () => request<Position[]>('/portfolio/positions'),
    history: (limit = 500) => request<PortfolioSnapshotPoint[]>(`/portfolio/history?limit=${limit}`),
  },

  signals: {
    list: (limit = 50, strategyId?: string) =>
      request<SignalRecord[]>(
        `/signals?limit=${limit}${strategyId ? `&strategy_id=${strategyId}` : ''}`
      ),
  },

  brokers: {
    list: () => request<BrokerConnection[]>('/brokers'),
    connect: (body: ConnectBrokerPayload) =>
      request<BrokerConnection>('/brokers', { method: 'POST', body: JSON.stringify(body) }),
    disconnect: (id: string) => request<void>(`/brokers/${id}`, { method: 'DELETE' }),
    account: (brokerId: string) => request(`/brokers/${brokerId}/account`),
    positions: (brokerId: string) => request(`/brokers/${brokerId}/positions`),
    placeOrder: (brokerId: string, body: PlaceOrderPayload) =>
      request<OrderResult>(`/brokers/${brokerId}/orders`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },

  // Placeholder — orders endpoint not yet implemented in backend
  orders: {
    list: (_params: { status?: string; page?: number; page_size?: number } = {}) =>
      Promise.resolve({ items: [] as Order[], total: 0 }),
  },

  strategies: {
    classes: () => request<StrategyClassDef[]>('/strategies/classes'),
    list: () => request<StrategyInstance[]>('/strategies'),
    create: (body: CreateStrategyPayload) =>
      request<StrategyInstance>('/strategies', { method: 'POST', body: JSON.stringify(body) }),
    updateStatus: (id: string, status: string) =>
      request<StrategyInstance>(`/strategies/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    delete: (id: string) => request<void>(`/strategies/${id}`, { method: 'DELETE' }),
  },

  backtests: {
    strategies: () => request<AvailableStrategiesResponse>('/backtests/strategies'),
    run: (body: BacktestRequest) =>
      request<BacktestResponse>('/backtests/run', { method: 'POST', body: JSON.stringify(body) }),
  },

  builder: {
    run: (body: {
      code: string
      symbol: string
      timeframe: string
      limit?: number
      initial_capital?: number
      commission_pct?: number
      parameters?: Record<string, unknown>
    }) => request<BacktestResponse>('/builder/run', { method: 'POST', body: JSON.stringify(body) }),

    generate: (body: { description: string; symbol: string; timeframe: string }) =>
      request<{ code: string; explanation: string }>('/builder/generate', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },
}
