import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MonteCarloPanel } from './MonteCarloPanel'
import type { MonteCarloResponse, PercentileStats } from '@/types/backtest'

function stats(p: Partial<PercentileStats>): PercentileStats {
  return { p5: 0, p25: 0, p50: 0, p75: 0, p95: 0, min: 0, max: 0, mean: 0, ...p }
}

const fixture: MonteCarloResponse = {
  strategy_name: 'SmaCrossover',
  symbol: 'BTCUSDT',
  timeframe: '1d',
  initial_capital: 10_000,
  n_simulations: 5_000,
  n_trades: 42,
  realized_total_return_pct: 12.5,
  drawdown_threshold_pct: 10,
  methods: {
    bootstrap: {
      method: 'bootstrap',
      final_equity: stats({ p50: 11_250 }),
      total_return_pct: stats({ p5: -8.2, p50: 12.5, p95: 40 }),
      max_drawdown_pct: stats({ p50: 9.5, p95: 21 }),
      prob_profit: 0.78,
      risk_of_exceeding_drawdown: 0.32,
      risk_of_ruin: 0,
      histogram: { edges: [-30, -10, 10, 30, 50], counts: [100, 900, 2500, 1500] },
    },
    shuffle: {
      method: 'shuffle',
      final_equity: stats({ p50: 11_250 }),
      total_return_pct: stats({ p5: 12.5, p50: 12.5, p95: 12.5 }),
      max_drawdown_pct: stats({ p50: 11, p95: 24 }),
      prob_profit: 1.0,
      risk_of_exceeding_drawdown: 0.55,
      risk_of_ruin: 0,
      histogram: { edges: [12, 13], counts: [5000] },
    },
  },
}

describe('MonteCarloPanel', () => {
  it('renders the bootstrap distribution by default', () => {
    render(<MonteCarloPanel result={fixture} />)
    expect(screen.getByText('+12.50%')).toBeInTheDocument()   // median return
    expect(screen.getByText('-8.20%')).toBeInTheDocument()    // 5th-pct return (1-in-20 bad run)
    expect(screen.getByText('78%')).toBeInTheDocument()       // probability of profit
  })

  it('switches to the shuffle distribution when the toggle is clicked', async () => {
    const user = userEvent.setup()
    render(<MonteCarloPanel result={fixture} />)

    await user.click(screen.getByRole('button', { name: /Shuffle/i }))

    expect(screen.getByText('100%')).toBeInTheDocument()      // shuffle prob-of-profit
    expect(screen.queryByText('78%')).not.toBeInTheDocument()
  })

  it('shows the simulation count and trade count', () => {
    render(<MonteCarloPanel result={fixture} />)
    expect(screen.getByText(/5000/)).toBeInTheDocument()
    expect(screen.getByText(/42/)).toBeInTheDocument()
  })
})
