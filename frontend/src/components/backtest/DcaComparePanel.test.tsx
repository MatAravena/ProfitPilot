import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DcaComparePanel } from './DcaComparePanel'
import type { DcaCompareResponse, DcaArmResult } from '@/types/backtest'

function arm(p: Partial<DcaArmResult>): DcaArmResult {
  return {
    equity_curve: [{ timestamp: 1_700_000_000_000, value: 1000 }],
    final_value: 0, total_contributed: 1000, total_return_pct: 0, units_accumulated: 0,
    avg_cost_basis: 0, max_drawdown_pct: 0, sharpe_ratio: 0, dry_powder: 0, realized_pnl: 0, ...p,
  }
}

const fixture: DcaCompareResponse = {
  symbol: 'BTCUSDT', timeframe: '1d', capital_model: 'contributions',
  caveat: 'Only ~3 completed halving cycles exist; read as one out-of-sample cycle, not proof.',
  cycle_markers: [{ timestamp: 1_700_000_000_000, kind: 'top' }],
  arms: {
    dca_flat: arm({ final_value: 1200, total_return_pct: 20, avg_cost_basis: 100 }),
    dca_dip_weighted_cycle: arm({ final_value: 1350, total_return_pct: 35, avg_cost_basis: 90 }),
    cycle_buydip_selltop: arm({ final_value: 1500, total_return_pct: 50, avg_cost_basis: 90 }),
    cycle_ath_trim_rebuy: arm({ final_value: 1420, total_return_pct: 42, avg_cost_basis: 80 }),
    dip_deploy_trim: arm({ final_value: 1600, total_return_pct: 60, avg_cost_basis: 70 }),
    cycle_selltop_redeploy_manual: arm({ final_value: 1700, total_return_pct: 70, avg_cost_basis: 65 }),
    cycle_selltop_redeploy_auto: arm({ final_value: 1650, total_return_pct: 65, avg_cost_basis: 68 }),
  },
}

describe('DcaComparePanel', () => {
  it('renders a row per arm with its total return', () => {
    render(<DcaComparePanel result={fixture} />)
    expect(screen.getByText('+20.00%')).toBeInTheDocument()
    expect(screen.getByText('+35.00%')).toBeInTheDocument()
    expect(screen.getByText('+50.00%')).toBeInTheDocument()
    expect(screen.getByText('+42.00%')).toBeInTheDocument()   // cycle_ath_trim_rebuy arm
    expect(screen.getByText('+60.00%')).toBeInTheDocument()   // dip_deploy_trim arm
    expect(screen.getByText('+70.00%')).toBeInTheDocument()   // cycle_selltop_redeploy_manual arm
    expect(screen.getByText('+65.00%')).toBeInTheDocument()   // cycle_selltop_redeploy_auto arm
  })

  it('shows the overfitting caveat', () => {
    render(<DcaComparePanel result={fixture} />)
    expect(screen.getByText(/one out-of-sample cycle, not proof/i)).toBeInTheDocument()
  })
})
