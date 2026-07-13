import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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

const makeTrades = (n: number): TradeRecord[] =>
  Array.from({ length: n }, (_, i) => ({
    ...mockTrade,
    side: i % 2 === 0 ? 'long' : 'short',
    entry_time: 1_700_000_000_000 + i * 1000,
    exit_time: 1_700_000_100_000 + i * 1000,
  }))

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

  it('does not show pagination controls when trades fit on one page', () => {
    render(<TradeTable trades={makeTrades(10)} pageSize={50} />)
    expect(screen.queryByLabelText('Next')).not.toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(10 + 1) // + header row
  })

  it('limits rows to pageSize and pages through the rest', () => {
    render(<TradeTable trades={makeTrades(120)} pageSize={50} />)
    expect(screen.getAllByRole('row')).toHaveLength(51) // 50 body + header
    expect(screen.getByText('1–50 of 120')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Next'))
    expect(screen.getByText('51–100 of 120')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Next'))
    expect(screen.getByText('101–120 of 120')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(21) // remaining 20 + header
  })

  it('disables Prev on the first page and Next on the last', () => {
    render(<TradeTable trades={makeTrades(60)} pageSize={50} />)
    expect(screen.getByLabelText('Prev')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Next'))
    expect(screen.getByLabelText('Next')).toBeDisabled()
  })
})
