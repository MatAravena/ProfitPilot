import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { setupServer } from 'msw/node'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'
import { Backtests } from './Backtests'

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderBacktests() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Backtests />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('Backtests page', () => {
  it('renders the page heading', () => {
    renderBacktests()
    expect(screen.getByText('Backtesting')).toBeInTheDocument()
  })

  it('loads and shows strategies in the selector', async () => {
    renderBacktests()
    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'SMA Crossover' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'RSI Mean Reversion' })).toBeInTheDocument()
    })
  })

  it('shows parameter inputs for the selected strategy', async () => {
    renderBacktests()
    await waitFor(() => {
      expect(screen.getByText('Fast Period')).toBeInTheDocument()
      expect(screen.getByText('Slow Period')).toBeInTheDocument()
    })
  })

  it('shows Run Backtest button', () => {
    renderBacktests()
    expect(screen.getByRole('button', { name: /Run Backtest/i })).toBeInTheDocument()
  })

  it('shows strategy description after selection', async () => {
    renderBacktests()
    await waitFor(() => {
      expect(screen.getByText('Golden/death cross strategy')).toBeInTheDocument()
    })
  })

  it('switches parameter inputs when a different strategy is selected', async () => {
    const user = userEvent.setup()
    renderBacktests()

    await waitFor(() => screen.getByRole('option', { name: 'RSI Mean Reversion' }))

    const strategyLabel = screen.getByText('Strategy')
    const select = strategyLabel.parentElement!.querySelector('select')!
    await user.selectOptions(select, 'RsiMeanReversion')

    await waitFor(() => {
      expect(screen.getByText('RSI Period')).toBeInTheDocument()
    })
  })

  it('Run Backtest button is disabled when no strategy loaded yet', () => {
    renderBacktests()
    const btn = screen.getByRole('button', { name: /Run Backtest/i })
    expect(btn).toBeDisabled()
  })
})
