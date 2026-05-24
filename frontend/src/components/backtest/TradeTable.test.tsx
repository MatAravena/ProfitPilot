import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { TradeRecord } from '@/types/backtest'
import { TradeTable } from './TradeTable'

const mockTrade: TradeRecord = {
  symbol: 'BTCUSDT',
  side: 'long',
  entry_price: 30000,
  exit_price: 31000,
  size: 0.1,
  pnl: 100,
  pnl_pct: 3.33,
  entry_time: 1700000000,
  exit_time: 1700086400,
}

describe('TradeTable', () => {
  it('renders nothing when trades array is empty', () => {
    const { container } = render(<TradeTable trades={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a row for each trade', () => {
    render(<TradeTable trades={[mockTrade, { ...mockTrade, side: 'short', pnl: -50, pnl_pct: -1.5 }]} />)
    expect(screen.getAllByRole('row')).toHaveLength(3) // 1 header + 2 body rows
  })

  it('shows trade side text', () => {
    render(<TradeTable trades={[mockTrade]} />)
    expect(screen.getByText('long')).toBeInTheDocument()
  })
})
