import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GridPanel } from './GridPanel'
import type { GridResponse, GridArmResult } from '@/types/backtest'

function arm(p: Partial<GridArmResult> = {}): GridArmResult {
  return {
    equity_curve: [
      { timestamp: 1_700_000_000_000, value: 10000 },
      { timestamp: 1_700_086_400_000, value: 10120 },
    ],
    final_equity: 10120, total_return_pct: 1.2, max_drawdown_pct: 3.4, sharpe_ratio: 0.9,
    grid_trades: 50, grid_realized_pnl: 260, forced_exit_pnl: 0, force_close_count: 0,
    mark_to_market_pnl: -140,
    avg_profit_per_grid_pct: 0.26, fill_rate: 52.7, time_in_grid_pct: 86,
    max_inventory_notional: 1052, worst_unrealized_pct: 4.1, time_underwater_pct: 40,
    ...p,
  }
}

const fixture: GridResponse = {
  symbol: 'BTCUSDT',
  timeframe: '1h',
  allow_intrabar_roundtrip: false,
  funding_rate_caveat:
    'SHORT_BIASED grid legs omit perp funding-rate cost. Realism gap disclosed, not fixed for v1.',
  arms: {
    grid_guarded_reanchor: arm({ final_equity: 10120, grid_realized_pnl: 260 }),
    grid_accumulate_nostop: arm({
      final_equity: 9800, total_return_pct: -2, grid_realized_pnl: 310,
      mark_to_market_pnl: -510, max_inventory_notional: 4200, worst_unrealized_pct: 12.5,
      time_underwater_pct: 71,
    }),
  },
}

describe('GridPanel', () => {
  it('renders a column per arm', () => {
    render(<GridPanel result={fixture} />)
    // The arm name legitimately appears twice — once in the attribution card, once in the
    // table's column header — so this checks presence, not a single unique match.
    expect(screen.getAllByText('Guarded re-anchor (bounded)').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Accumulate, no stop (unbounded)').length).toBeGreaterThan(0)
  })

  it('always shows the funding-rate caveat', () => {
    render(<GridPanel result={fixture} />)
    expect(screen.getByText(/omit perp funding-rate cost/i)).toBeInTheDocument()
  })

  it('splits realized grid income from inventory mark-to-market', () => {
    render(<GridPanel result={fixture} />)
    // The attribution block labels both halves rather than showing one blended number.
    expect(screen.getAllByText(/Grid income \(realized\)/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Inventory mark-to-market/i).length).toBeGreaterThan(0)
    // The no-stop arm's negative mark-to-market must be visible, not hidden.
    expect(screen.getByText('-$510.00')).toBeInTheDocument()
  })

  it('surfaces the unbounded arm disclosure metrics', () => {
    render(<GridPanel result={fixture} />)
    expect(screen.getByText('Peak inventory')).toBeInTheDocument()
    expect(screen.getByText('Worst unrealized')).toBeInTheDocument()
    expect(screen.getByText('Time underwater')).toBeInTheDocument()
  })

  it('renders only the arms present in the response', () => {
    const oneArm: GridResponse = {
      ...fixture,
      arms: { grid_guarded_reanchor: fixture.arms.grid_guarded_reanchor },
    }
    render(<GridPanel result={oneArm} />)
    expect(screen.getAllByText('Guarded re-anchor (bounded)').length).toBeGreaterThan(0)
    expect(screen.queryByText('Accumulate, no stop (unbounded)')).toBeNull()
  })
})
