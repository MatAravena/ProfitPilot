import type {
  OrderResult,
  PlaceOrderPayload,
  Position,
  OHLCVCandle,
  BrokerConnection,
  ConnectBrokerPayload,
  StrategyInstance,
  StrategyClassDef,
  CreateStrategyPayload,
  ExecutionConfig,
  RiskProfile,
  SignalRecord,
  OrderRecord,
  PortfolioSnapshotPoint,
} from '@/types'
import type {
  BacktestRequest,
  BacktestResponse,
  PortfolioSummary,
  AvailableStrategiesResponse,
} from '@/types/backtest'

import { ApiError, ErrorCode, type FieldError } from '@/lib/errors'

const BASE_URL = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    throw await parseError(res)
  }
  // 204 No Content etc. — nothing to parse.
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** Parse the backend's structured `{ error: { code, message, details } }` body. */
async function parseError(res: Response): Promise<ApiError> {
  const fallbackCode = res.status === 404 ? ErrorCode.NotFound : ErrorCode.BadRequest
  const raw = await res.text()
  if (!raw) return new ApiError(fallbackCode, `HTTP ${res.status}`, res.status)

  try {
    const body = JSON.parse(raw)
    const e = body?.error
    if (e && typeof e === 'object') {
      const fields = e.details?.fields as FieldError[] | undefined
      return new ApiError(
        e.code ?? fallbackCode,
        e.message ?? `HTTP ${res.status}`,
        res.status,
        fields,
      )
    }
    // Legacy `{ detail: "..." }` shape (plain FastAPI HTTPException).
    if (typeof body?.detail === 'string') {
      return new ApiError(fallbackCode, body.detail, res.status)
    }
  } catch {
    // Non-JSON body — fall through to raw text.
  }
  return new ApiError(fallbackCode, raw, res.status)
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

  orders: {
    // User-wide order history (order_records), newest first, paginated.
    list: (limit = 25, offset = 0) =>
      request<{ items: OrderRecord[]; total: number }>(`/orders?limit=${limit}&offset=${offset}`),
  },

  strategies: {
    classes: () => request<StrategyClassDef[]>('/strategies/classes'),
    list: () => request<StrategyInstance[]>('/strategies'),
    orders: (id: string, limit = 200) =>
      request<OrderRecord[]>(`/strategies/${id}/orders?limit=${limit}`),
    create: (body: CreateStrategyPayload) =>
      request<StrategyInstance>('/strategies', { method: 'POST', body: JSON.stringify(body) }),
    updateStatus: (id: string, status: string) =>
      request<StrategyInstance>(`/strategies/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    updateConfig: (id: string, body: ExecutionConfig) =>
      request<StrategyInstance>(`/strategies/${id}/config`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    delete: (id: string) => request<void>(`/strategies/${id}`, { method: 'DELETE' }),
  },

  settings: {
    getRisk: () => request<RiskProfile>('/settings/risk'),
    updateRisk: (body: RiskProfile) =>
      request<RiskProfile>('/settings/risk', { method: 'PUT', body: JSON.stringify(body) }),
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
