import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { WalkForwardPanel } from './WalkForwardPanel'
import type { WalkForwardResponse } from '@/types/backtest'

const DAY = 86_400_000
const T0 = Date.UTC(2020, 0, 1)

function fixture(over: Partial<WalkForwardResponse> = {}): WalkForwardResponse {
  return {
    strategy_name: 'TrendFilter', symbol: 'BTCUSDT', timeframe: '1d', objective: 'sharpe_ratio',
    initial_capital: 10_000, train_bars: 730, test_bars: 180, combinations: 3, skipped_combinations: 0,
    oos_total_return_pct: 120, oos_max_drawdown_pct: 30, oos_sharpe: 1.2,
    buy_hold_total_return_pct: 150, buy_hold_max_drawdown_pct: 75,
    pct_folds_profitable: 75, avg_is_score: 1.6, avg_oos_sharpe: 1.1, distinct_param_sets: 2,
    passes_bar: true,
    folds: [
      { train_start: T0, train_end: T0 + 729 * DAY, test_start: T0 + 730 * DAY, test_end: T0 + 909 * DAY,
        params: { period: 100 }, is_score: 1.7, is_return_pct: 80, oos_return_pct: 25.5,
        oos_sharpe: 1.4, oos_max_drawdown_pct: 12, oos_trades: 3, buy_hold_return_pct: 30 },
      { train_start: T0 + 180 * DAY, train_end: T0 + 909 * DAY, test_start: T0 + 910 * DAY,
        test_end: T0 + 1089 * DAY, params: { period: 150 }, is_score: 1.5, is_return_pct: 60,
        oos_return_pct: -4.2, oos_sharpe: -0.3, oos_max_drawdown_pct: 15, oos_trades: 2,
        buy_hold_return_pct: -20 },
    ],
    equity_curve: [{ timestamp: T0 + 730 * DAY, value: 10_000 }, { timestamp: T0 + 1089 * DAY, value: 22_000 }],
    buy_hold_curve: [{ timestamp: T0 + 730 * DAY, value: 10_000 }, { timestamp: T0 + 1089 * DAY, value: 25_000 }],
    caveat: 'Only the out-of-sample columns count.',
    ...over,
  }
}

describe('WalkForwardPanel', () => {
  it('shows the verdict, the out-of-sample numbers next to buy & hold, and every fold', () => {
    render(<WalkForwardPanel result={fixture()} />)
    expect(screen.getByText(/passes/i)).toBeTruthy()
    expect(screen.getByText('+120.00%')).toBeTruthy()
    expect(screen.getByText('period=100')).toBeTruthy()
    expect(screen.getByText('period=150')).toBeTruthy()
    expect(screen.getByText('-4.20%')).toBeTruthy()
    expect(screen.getByText('Only the out-of-sample columns count.')).toBeTruthy()
  })

  it('says so plainly when the strategy does not pass', () => {
    render(<WalkForwardPanel result={fixture({ passes_bar: false })} />)
    expect(screen.getByText(/does not pass/i)).toBeTruthy()
  })
})
