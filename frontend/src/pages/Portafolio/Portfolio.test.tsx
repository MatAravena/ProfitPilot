import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
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
})
