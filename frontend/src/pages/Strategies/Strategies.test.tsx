import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'
import { Strategies } from './Strategies'

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
})
