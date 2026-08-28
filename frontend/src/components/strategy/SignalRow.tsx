import { useTranslation } from 'react-i18next'
import { cn, formatCurrency } from '@/lib/utils'
import type { SignalRecord } from '@/types'

export const DIRECTION_CONFIG = {
  long:    { label: 'LONG',  className: 'bg-success/15 text-success' },
  short:   { label: 'SHORT', className: 'bg-danger/15 text-danger' },
  close:   { label: 'CLOSE', className: 'bg-warning/15 text-warning' },
  neutral: { label: 'HOLD',  className: 'bg-surface-2 text-text-muted' },
}

/** One row of the live/historical signal feed — shared by Dashboard and StrategyDetail. */
export function SignalRow({ s }: { s: SignalRecord }) {
  const { t } = useTranslation()
  const cfg = DIRECTION_CONFIG[s.direction as keyof typeof DIRECTION_CONFIG] ?? DIRECTION_CONFIG.neutral
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/50 hover:bg-surface-2 transition-colors">
      <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0', cfg.className)}>
        {cfg.label}
      </span>
      <span className="font-mono text-xs font-medium text-text">{s.symbol}</span>
      <span className="text-[11px] text-text-muted">{s.timeframe}</span>
      {s.close_price != null && (
        <span className="text-[11px] text-text-muted ml-auto shrink-0">
          @ {formatCurrency(s.close_price)}
        </span>
      )}
      <span className="text-[10px] text-text-muted shrink-0 w-14 text-right">
        {t('dashboard.conf', { pct: Math.round(s.confidence * 100) })}
      </span>
      <span className="text-[10px] text-text-muted shrink-0 w-14 text-right">
        {new Date(s.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </span>
    </div>
  )
}
