import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { setupServer } from 'msw/node'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { handlers } from '@/test/msw-handlers'

// BacktestChart is canvas-based (lightweight-charts) — stub it for jsdom, same as
// StrategyDetail.test.tsx does for TradingChart. Needed now because these are the first tests
// in this file to drive a real run-to-result flow (prior tests never got past the input stage).
vi.mock('@/components/backtest/BacktestChart', () => ({
  BacktestChart: () => <div data-testid="backtest-chart" />,
}))

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

  it('shows the grid controls once a backtest has run', async () => {
    const user = userEvent.setup()
    renderBacktests()

    await waitFor(() => screen.getByRole('option', { name: 'SMA Crossover' }))
    await user.click(screen.getByRole('button', { name: /Run Backtest/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /run grid backtest/i })).toBeInTheDocument()
    })
  })

  it('runs a grid backtest and renders the panel with both arms', async () => {
    const user = userEvent.setup()
    renderBacktests()

    await waitFor(() => screen.getByRole('option', { name: 'SMA Crossover' }))
    await user.click(screen.getByRole('button', { name: /Run Backtest/i }))
    await waitFor(() => screen.getByRole('button', { name: /run grid backtest/i }))

    await user.click(screen.getByRole('button', { name: /run grid backtest/i }))

    await waitFor(() => {
      expect(screen.getAllByText('Guarded re-anchor (bounded)').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Accumulate, no stop (unbounded)').length).toBeGreaterThan(0)
      expect(screen.getByText(/omit perp funding-rate cost/i)).toBeInTheDocument()
    })
  })
})
