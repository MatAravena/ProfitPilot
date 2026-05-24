import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'

vi.mock('@monaco-editor/react', () => ({
  default: ({ value }: { value: string }) => <textarea data-testid="monaco-editor">{value}</textarea>,
}))

import { Builder } from './Builder'

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderBuilder() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Builder />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('Builder page', () => {
  it('renders the page heading', () => {
    renderBuilder()
    expect(screen.getByText('Strategy Builder')).toBeInTheDocument()
  })

  it('renders the code editor', () => {
    renderBuilder()
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument()
  })

  it('renders the Run Backtest button', () => {
    renderBuilder()
    expect(screen.getByRole('button', { name: /run backtest/i })).toBeInTheDocument()
  })
})
