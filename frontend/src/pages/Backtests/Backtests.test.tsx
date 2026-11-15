import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
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

  it('runs a walk-forward around the backtested parameters and shows the verdict', async () => {
    let sent: Record<string, unknown> | null = null
    server.use(
      http.post('/api/v1/backtests/walk-forward', async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          strategy_name: 'SmaCrossover', symbol: 'BTCUSDT', timeframe: '1d', objective: 'sharpe_ratio',
          initial_capital: 10000, train_bars: 730, test_bars: 180, combinations: 9, skipped_combinations: 0,
          oos_total_return_pct: 5, oos_max_drawdown_pct: 20, oos_sharpe: 0.2,
          buy_hold_total_return_pct: 60, buy_hold_max_drawdown_pct: 40, pct_folds_profitable: 40,
          avg_is_score: 1.4, avg_oos_sharpe: 0.1, distinct_param_sets: 3, passes_bar: false, folds: [],
          equity_curve: [], buy_hold_curve: [], caveat: 'Only the out-of-sample columns count.',
        })
      }),
    )
    const user = userEvent.setup()
    renderBacktests()

    await waitFor(() => screen.getByRole('option', { name: 'SMA Crossover' }))
    await user.click(screen.getByRole('button', { name: /Run Backtest/i }))
    await waitFor(() => screen.getByRole('button', { name: /run walk-forward/i }))
    await user.click(screen.getByRole('button', { name: /run walk-forward/i }))

    await waitFor(() => expect(screen.getByText(/does not pass/i)).toBeInTheDocument())
    expect(sent).toMatchObject({
      strategy_name: 'SmaCrossover',
      parameters: {},
      param_grid: { fast_period: [10, 20, 30], slow_period: [25, 50, 75] },
      train_days: 730,
      test_days: 180,
    })
  })
})
