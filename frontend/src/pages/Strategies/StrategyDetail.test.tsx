import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'

// TradingChart is canvas-based (lightweight-charts) — stub it for jsdom.
vi.mock('@/components/charts/TradingChart', () => ({
  TradingChart: () => <div data-testid="trading-chart" />,
}))

// Mock the WebSocket singleton; spies are hoisted so they're safe in the factory.
const { wsOn, wsSubscribe, wsUnsubscribe } = vi.hoisted(() => ({
  wsOn: vi.fn(() => vi.fn()),
  wsSubscribe: vi.fn(),
  wsUnsubscribe: vi.fn(),
}))
vi.mock('@/lib/websocket', () => ({
  tradingWS: { on: wsOn, subscribe: wsSubscribe, unsubscribe: wsUnsubscribe },
}))

import { StrategyDetail } from './StrategyDetail'

const sampleStrategy = {
  id: 's1', class_name: 'SmaCrossover', label: 'My SMA', symbol: 'BTCUSDT',
  timeframe: '1d', broker_connection_id: null, status: 'paper', parameters: {},
  execution: {
    size_pct: 0.02, stop_loss_pct: 0.015, take_profit_pct: null,
    max_open_positions: 5, max_daily_drawdown_pct: 0.03, max_total_drawdown_pct: 0.1,
    max_orders_per_minute: 10, allow_short: true, kill_switch_enabled: true, poll_seconds: null,
  },
  created_at: '', updated_at: '', last_signal_at: null, error_count: 0,
}

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => { server.resetHandlers(); vi.clearAllMocks() })
afterAll(() => server.close())

function renderDetail() {
  server.use(http.get('/api/v1/strategies', () => HttpResponse.json([sampleStrategy])))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/strategies/s1']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetail />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('StrategyDetail page', () => {
  it('renders the strategy header and chart', async () => {
    renderDetail()
    expect(await screen.findByText('My SMA')).toBeInTheDocument()
    expect(screen.getByTestId('trading-chart')).toBeInTheDocument()
  })

  it('renders the order-history section', async () => {
    renderDetail()
    expect(await screen.findByText('Order history')).toBeInTheDocument()
  })

  it('subscribes to strategy channels on mount and cleans up on unmount', async () => {
    const { unmount } = renderDetail()
    await screen.findByText('My SMA')
    expect(wsSubscribe).toHaveBeenCalledWith('strategy.order')
    expect(wsSubscribe).toHaveBeenCalledWith('strategy.signal')
    unmount()
    expect(wsUnsubscribe).toHaveBeenCalledWith('strategy.order')
    expect(wsUnsubscribe).toHaveBeenCalledWith('strategy.signal')
  })
})
