import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import type { TradeRecord } from '@/types/backtest'

interface Props {
  trades: TradeRecord[]
  /** Rows per page; pagination controls appear only when trades exceed this. */
  pageSize?: number
}

export function TradeTable({ trades, pageSize = 50 }: Props) {
  const { t } = useTranslation()
  const [page, setPage] = useState(0)

  const pageCount = Math.max(1, Math.ceil(trades.length / pageSize))
  // Clamp the page if the trade list shrank (e.g. a new backtest with fewer trades).
  const safePage = Math.min(page, pageCount - 1)
  const visible = useMemo(
    () => trades.slice(safePage * pageSize, safePage * pageSize + pageSize),
    [trades, safePage, pageSize],
  )

  if (trades.length === 0) return null

  const paginated = trades.length > pageSize
  const from = safePage * pageSize + 1
  const to = Math.min(safePage * pageSize + pageSize, trades.length)

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{t('backtests.tradeHistory', { count: trades.length })}</span>
        {paginated && (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="tabular-nums">{t('backtests.pagination.showing', { from, to, total: trades.length })}</span>
            <button
              type="button"
              onClick={() => setPage(safePage - 1)}
              disabled={safePage === 0}
              className="p-1 rounded border border-border hover:bg-surface-2 disabled:opacity-40 disabled:hover:bg-transparent transition-colors"
              aria-label={t('backtests.pagination.prev')}
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              onClick={() => setPage(safePage + 1)}
              disabled={safePage >= pageCount - 1}
              className="p-1 rounded border border-border hover:bg-surface-2 disabled:opacity-40 disabled:hover:bg-transparent transition-colors"
              aria-label={t('backtests.pagination.next')}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto max-h-72 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-border">
              {(['side', 'entry', 'exit', 'size', 'pnl', 'pnlPct'] as const).map((k) => (
                <th key={k} className="px-3 py-2 text-left text-text-muted font-medium">
                  {t(`backtests.table.${k}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((tr, i) => (
              <tr key={`${tr.entry_time}-${tr.exit_time}-${safePage}-${i}`} className="border-b border-border/40 hover:bg-surface-2 transition-colors">
                <td className={cn('px-3 py-2 font-medium uppercase', tr.side === 'long' ? 'text-success' : 'text-danger')}>
                  {tr.side}
                </td>
                <td className="px-3 py-2">{formatCurrency(tr.entry_price)}</td>
                <td className="px-3 py-2">{formatCurrency(tr.exit_price)}</td>
                <td className="px-3 py-2">{tr.size.toFixed(6)}</td>
                <td className={cn('px-3 py-2 font-medium', tr.pnl >= 0 ? 'text-success' : 'text-danger')}>
                  {formatCurrency(tr.pnl)}
                </td>
                <td className={cn('px-3 py-2', tr.pnl_pct >= 0 ? 'text-success' : 'text-danger')}>
                  {formatPercent(tr.pnl_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
