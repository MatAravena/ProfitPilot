import { useTranslation } from 'react-i18next'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import type { TradeRecord } from '@/types/backtest'

interface Props {
  trades: TradeRecord[]
}

export function TradeTable({ trades }: Props) {
  const { t } = useTranslation()

  if (trades.length === 0) return null

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <span className="text-sm font-medium">{t('backtests.tradeHistory', { count: trades.length })}</span>
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
            {trades.map((tr, i) => (
              <tr key={`${tr.entry_time}-${tr.exit_time}-${i}`} className="border-b border-border/40 hover:bg-surface-2 transition-colors">
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
