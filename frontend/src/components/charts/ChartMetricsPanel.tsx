import type { OHLCVCandle } from '@/types'
import type { PortfolioPosition } from '@/types/backtest'
import type { CrosshairSnapshot } from './TradingChart'
import { formatCurrency, formatNumber, formatPercent, cn } from '@/lib/utils'

interface Props {
  symbol: string
  candles: OHLCVCandle[]
  /** Live crosshair readout; when null we fall back to the latest candle. */
  hover: CrosshairSnapshot | null
  position?: PortfolioPosition
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-text-muted">{label}</span>
      <span className={cn('text-xs font-medium tabular-nums', className ?? 'text-text')}>{value}</span>
    </div>
  )
}

export function ChartMetricsPanel({ symbol, candles, hover, position }: Props) {
  if (!candles.length) {
    return <div className="text-xs text-text-muted">No data.</div>
  }

  const last = candles[candles.length - 1]
  const first = candles[0]
  // Use the hovered candle's OHLC when present, otherwise the latest bar.
  const bar = hover ?? { ...last, indicators: {} as Record<string, number> }

  const change = bar.close - first.open
  const changePct = first.open !== 0 ? (change / first.open) * 100 : 0
  const up = change >= 0
  const periodHigh = Math.max(...candles.map((c) => c.high))
  const periodLow = Math.min(...candles.map((c) => c.low))
  const totalVol = candles.reduce((s, c) => s + c.volume, 0)
  const indicatorEntries = Object.entries(bar.indicators)

  return (
    <div className="space-y-4">
      {/* Price header */}
      <div>
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-semibold text-text">{symbol}</span>
          <span className="text-[10px] text-text-muted">
            {hover ? 'hovered' : 'last'}
          </span>
        </div>
        <div className="mt-0.5 flex items-baseline gap-2">
          <span className="text-xl font-bold tabular-nums text-text">{formatCurrency(bar.close)}</span>
          <span className={cn('text-xs font-medium', up ? 'text-success' : 'text-danger')}>
            {formatPercent(changePct)}
          </span>
        </div>
      </div>

      {/* OHLC */}
      <div className="space-y-1 rounded-lg border border-border bg-surface-2/40 p-2.5">
        <Stat label="Open" value={formatCurrency(bar.open)} />
        <Stat label="High" value={formatCurrency(bar.high)} className="text-success" />
        <Stat label="Low" value={formatCurrency(bar.low)} className="text-danger" />
        <Stat label="Close" value={formatCurrency(bar.close)} />
        <Stat label="Volume" value={formatNumber(bar.volume, 0)} />
      </div>

      {/* Range / aggregate */}
      <div className="space-y-1 rounded-lg border border-border bg-surface-2/40 p-2.5">
        <Stat label="Period High" value={formatCurrency(periodHigh)} />
        <Stat label="Period Low" value={formatCurrency(periodLow)} />
        <Stat label="Total Vol" value={formatNumber(totalVol, 0)} />
      </div>

      {/* Live indicator readouts */}
      {indicatorEntries.length > 0 && (
        <div className="space-y-1 rounded-lg border border-border bg-surface-2/40 p-2.5">
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Indicators</h4>
          {indicatorEntries.map(([label, value]) => (
            <Stat key={label} label={label} value={formatNumber(value, 2)} />
          ))}
        </div>
      )}

      {/* Open position / P&L for this symbol */}
      <div className="space-y-1 rounded-lg border border-border bg-surface-2/40 p-2.5">
        <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Position</h4>
        {position ? (
          <>
            <Stat label="Qty" value={formatNumber(position.quantity, 4)} />
            <Stat label="Avg Entry" value={formatCurrency(position.avg_entry_price)} />
            <Stat label="Mark" value={formatCurrency(position.current_price)} />
            <Stat
              label="Unrealized P&L"
              value={`${formatCurrency(position.unrealized_pnl)} (${formatPercent(position.unrealized_pnl_pct)})`}
              className={position.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}
            />
          </>
        ) : (
          <p className="text-[11px] text-text-muted">No open position.</p>
        )}
      </div>
    </div>
  )
}
