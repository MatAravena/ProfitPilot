import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'
import { Strategies } from './Strategies'

const sampleStrategy = {
  id: 's1', class_name: 'SmaCrossover', label: 'My SMA', symbol: 'BTCUSDT',
  timeframe: '1d', broker_connection_id: null, status: 'draft', parameters: {},
  execution: {
    size_pct: 0.02, stop_loss_pct: 0.015, take_profit_pct: null,
    max_open_positions: 5, max_daily_drawdown_pct: 0.03, max_total_drawdown_pct: 0.1,
    max_orders_per_minute: 10, allow_short: true, kill_switch_enabled: true, poll_seconds: null,
  },
  created_at: '', updated_at: '', last_signal_at: null, error_count: 0,
}

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderStrategies() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Strategies />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('Strategies page', () => {
  it('renders the page heading', () => {
    renderStrategies()
    expect(screen.getByText('Strategies')).toBeInTheDocument()
  })

  it('renders the New Strategy button', () => {
    renderStrategies()
    expect(screen.getByRole('button', { name: /new strategy/i })).toBeInTheDocument()
  })

  it('shows the config summary and opens the edit-config dialog', async () => {
    server.use(http.get('/api/v1/strategies', () => HttpResponse.json([sampleStrategy])))
    renderStrategies()

    // Summary chip renders the position size as a percent (0.02 → 2%).
    expect(await screen.findByText('2%')).toBeInTheDocument()

    // Clicking the edit-config button opens the dialog with the config form.
    fireEvent.click(await screen.findByTitle('Edit config'))
    expect(await screen.findByText('Position size')).toBeInTheDocument()
    expect(screen.getByText('Allow short')).toBeInTheDocument()
  })
})
