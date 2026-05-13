import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { TrendingUp, TrendingDown, DollarSign, Activity, Layers, Zap } from 'lucide-react'
import { useUIStore } from '@/stores/ui'
import { useSignalsStore } from '@/stores/signals'
import { api } from '@/lib/api'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import type { SignalRecord } from '@/types'
import { PriceChart } from '@/components/charts/PriceChart'

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'] as const

const DEFAULT_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
  'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'ARBUSDT',
]

const DIRECTION_CONFIG = {
  long:    { label: 'LONG',  className: 'bg-success/15 text-success' },
  short:   { label: 'SHORT', className: 'bg-danger/15 text-danger' },
  close:   { label: 'CLOSE', className: 'bg-warning/15 text-warning' },
  neutral: { label: 'HOLD',  className: 'bg-surface-2 text-text-muted' },
}

function SignalRow({ s }: { s: SignalRecord }) {
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

export function Dashboard() {
  const { t } = useTranslation()
  const { activeTimeframe, setTimeframe } = useUIStore()
  const liveSignals = useSignalsStore((s) => s.liveSignals)
  const setSignals = useSignalsStore((s) => s.setSignals)

  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT')
  const [customSymbol, setCustomSymbol] = useState('')

  const { data: portfolio } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: api.portfolio.summary,
    staleTime: 30_000,
    retry: false,
  })

  const { data: recentSignals } = useQuery({
    queryKey: ['signals', 'recent'],
    queryFn: () => api.signals.list(20),
    staleTime: 30_000,
  })
  useEffect(() => {
    if (recentSignals?.length) setSignals(recentSignals)
  }, [recentSignals, setSignals])

  const equity = portfolio?.total_equity ?? 0
  const unrealizedPnl = portfolio?.total_unrealized_pnl ?? 0
  const positions = portfolio?.positions ?? []
  const pnlPositive = unrealizedPnl >= 0

  const kpis = [
    {
      label: t('dashboard.kpis.equity'),
      value: formatCurrency(equity),
      icon: DollarSign,
      subValue: formatPercent((unrealizedPnl / (equity || 1)) * 100),
      positive: pnlPositive,
    },
    {
      label: t('dashboard.kpis.unrealizedPnl'),
      value: formatCurrency(unrealizedPnl),
      icon: pnlPositive ? TrendingUp : TrendingDown,
      subValue: t('dashboard.subs.openPositions'),
      positive: pnlPositive,
    },
    {
      label: t('dashboard.kpis.cash'),
      value: formatCurrency(portfolio?.total_cash ?? 0),
      icon: Activity,
      subValue: t('dashboard.subs.available'),
      positive: true,
    },
    {
      label: t('dashboard.kpis.accounts'),
      value: String(portfolio?.accounts.length ?? 0),
      icon: TrendingUp,
      subValue: t('dashboard.subs.connectedBrokers'),
      positive: true,
    },
    {
      label: t('dashboard.kpis.positions'),
      value: String(positions.length),
      icon: Layers,
      subValue: t('dashboard.subs.active'),
      positive: true,
    },
  ]

  const tableHeaders = [
    t('dashboard.table.symbol'), t('dashboard.table.broker'), t('dashboard.table.size'),
    t('dashboard.table.entry'), t('dashboard.table.current'), t('dashboard.table.unrealizedPnl'),
  ]

  return (
    <div className="p-6 flex flex-col gap-6 animate-fade-in">
      {/* KPI row */}
      <div className="grid grid-cols-5 gap-4">
        {kpis.map(({ label, value, icon: Icon, subValue, positive }) => (
          <div key={label} className="bg-surface border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-text-muted font-medium">{label}</span>
              <Icon size={14} className="text-text-muted" strokeWidth={1.5} />
            </div>
            <p className="text-xl font-bold">{value}</p>
            <p className={cn('text-xs mt-1', positive ? 'text-success' : 'text-danger')}>{subValue}</p>
          </div>
        ))}
      </div>

      {/* Chart + Live signals */}
      <div className="grid grid-cols-[1fr_300px] gap-4">
        <div className="bg-surface border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border overflow-x-auto">
            {DEFAULT_SYMBOLS.map((sym) => (
              <button
                key={sym}
                onClick={() => { setActiveSymbol(sym); setCustomSymbol('') }}
                className={cn(
                  'px-2.5 py-1 text-xs rounded font-mono font-medium whitespace-nowrap transition-colors cursor-pointer shrink-0',
                  activeSymbol === sym && !customSymbol
                    ? 'bg-primary text-white'
                    : 'text-text-muted hover:text-text hover:bg-surface-2',
                )}
              >
                {sym.replace('USDT', '/USDT')}
              </button>
            ))}
            <input
              type="text"
              placeholder={t('dashboard.customPlaceholder')}
              value={customSymbol}
              onChange={(e) => {
                const v = e.target.value.toUpperCase()
                setCustomSymbol(v)
                if (v) setActiveSymbol(v)
              }}
              className={cn(
                'ml-1 w-24 shrink-0 bg-background border rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary',
                customSymbol ? 'border-primary text-text' : 'border-border text-text-muted',
              )}
            />
          </div>
          <div className="flex items-center gap-1 px-4 py-2 border-b border-border">
            <span className="text-xs font-medium text-text mr-2">{activeSymbol}</span>
            <div className="flex items-center gap-1 ml-auto">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={cn(
                    'px-2.5 py-1 text-xs rounded font-medium transition-colors cursor-pointer',
                    activeTimeframe === tf
                      ? 'bg-primary text-white'
                      : 'text-text-muted hover:text-text hover:bg-surface-2',
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <PriceChart symbol={activeSymbol} timeframe={activeTimeframe} />
        </div>

        {/* Live signals feed */}
        <div className="bg-surface border border-border rounded-xl overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2 shrink-0">
            <Zap size={13} className="text-primary" />
            <span className="text-sm font-medium">{t('dashboard.liveSignals')}</span>
            {liveSignals.length > 0 && (
              <span className="ml-auto text-[10px] text-text-muted">{liveSignals.length}</span>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {liveSignals.length === 0 ? (
              <div className="px-4 py-10 text-center text-text-muted text-xs">
                <p>{t('dashboard.noSignals')}</p>
                <p className="mt-1">{t('dashboard.noSignalsHint')}</p>
              </div>
            ) : (
              liveSignals.map((s) => <SignalRow key={s.id} s={s} />)
            )}
          </div>
        </div>
      </div>

      {/* Open positions table */}
      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <span className="text-sm font-medium">{t('dashboard.openPositions')}</span>
        </div>
        {positions.length === 0 ? (
          <div className="px-4 py-8 text-center text-text-muted text-sm">{t('dashboard.noPositions')}</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {tableHeaders.map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs text-text-muted font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-surface-2 transition-colors">
                  <td className="px-4 py-3 font-medium">{p.symbol}</td>
                  <td className="px-4 py-3 text-text-muted capitalize">{p.broker_id}</td>
                  <td className="px-4 py-3">{p.quantity}</td>
                  <td className="px-4 py-3">{formatCurrency(p.avg_entry_price)}</td>
                  <td className="px-4 py-3">{formatCurrency(p.current_price)}</td>
                  <td className={cn('px-4 py-3 font-medium', p.unrealized_pnl >= 0 ? 'text-success' : 'text-danger')}>
                    {formatCurrency(p.unrealized_pnl)} ({formatPercent(p.unrealized_pnl_pct)})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
