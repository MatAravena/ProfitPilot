import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'
import { Portfolio } from './Portfolio'

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPortfolio() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Portfolio />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('Portfolio page', () => {
  it('renders the Total Equity KPI', () => {
    renderPortfolio()
    expect(screen.getByText('Total Equity')).toBeInTheDocument()
  })

  it('renders the Open Positions section', () => {
    renderPortfolio()
    expect(screen.getByText('Open Positions')).toBeInTheDocument()
  })

  it('renders the Place Order section', () => {
    renderPortfolio()
    expect(screen.getByText('Place Order')).toBeInTheDocument()
  })

  it('renders the Order History section with its empty state', async () => {
    renderPortfolio()
    expect(screen.getByText('Order History')).toBeInTheDocument()
    expect(await screen.findByText(/No orders yet/i)).toBeInTheDocument()
  })

  it('shows pagination and pages through order history', async () => {
    const page0 = Array.from({ length: 25 }, (_, i) => ({
      id: `o${i}`, symbol: 'BTCUSDT', side: 'buy', quantity: 0.1, status: 'opened_long',
      reason: null, avg_price: 30000 + i, filled_qty: 0.1, realized_pnl: null,
      signal_id: null, created_at: '2024-01-01T00:00:00Z',
    }))
    server.use(
      http.get('/api/v1/orders', ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get('offset') ?? 0)
        return HttpResponse.json({ items: offset === 0 ? page0 : page0.slice(0, 5), total: 30 })
      }),
    )
    renderPortfolio()
    expect(await screen.findByText('1–25 of 30')).toBeInTheDocument()
    const next = screen.getByLabelText('Next')
    expect(next).not.toBeDisabled()
    next.click()
    expect(await screen.findByText('26–30 of 30')).toBeInTheDocument()
  })
})
