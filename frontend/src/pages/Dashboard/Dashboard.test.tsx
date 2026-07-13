import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'
import { Dashboard } from './Dashboard'

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Dashboard />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('Dashboard page', () => {
  it('renders the Live Signals section', () => {
    renderDashboard()
    expect(screen.getByText('Live Signals')).toBeInTheDocument()
  })

  it('renders the Open Positions section', () => {
    renderDashboard()
    expect(screen.getAllByText('Open Positions').length).toBeGreaterThan(0)
  })

  it('renders the Portfolio Equity KPI label', () => {
    renderDashboard()
    expect(screen.getByText('Portfolio Equity')).toBeInTheDocument()
  })

  it('renders the Equity Curve card with its empty state when there is no history', async () => {
    renderDashboard()
    expect(screen.getByText('Equity Curve')).toBeInTheDocument()
    expect(await screen.findByText(/No equity history yet/i)).toBeInTheDocument()
  })
})
