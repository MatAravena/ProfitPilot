import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Play, TrendingUp, TrendingDown, Activity, BarChart2, Award, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import type { BacktestRequest, BacktestResponse, BacktestMetrics, StrategyMeta } from '@/types/backtest'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import { EquityChart } from '@/components/charts/EquityChart'

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'] as const
const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

function defaultParams(meta: StrategyMeta | undefined): Record<string, number> {
  if (!meta) return {}
  return Object.fromEntries((meta.parameters ?? []).map((p) => [p.key, p.default]))
}

export function Backtests() {
  const { t } = useTranslation()
  const [form, setForm] = useState<BacktestRequest>({
    strategy_name: '',
    symbol: 'BTCUSDT',
    timeframe: '1d',
    initial_capital: 10000,
    commission_pct: 0.001,
    parameters: {},
  })
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [result, setResult] = useState<BacktestResponse | null>(null)

  const { data: available } = useQuery({
    queryKey: ['backtests', 'strategies'],
    queryFn: api.backtests.strategies,
    staleTime: Infinity,
  })

  const run = useMutation({
    mutationFn: (req: BacktestRequest) => api.backtests.run(req),
    onSuccess: (data) => setResult(data),
  })

  useEffect(() => {
    if (available?.strategies.length && !form.strategy_name) {
      const first = available.strategies[0]
      setForm((f) => ({ ...f, strategy_name: first.class_name, parameters: defaultParams(first) }))
    }
  }, [available])

  function handleStrategyChange(name: string) {
    const meta = available?.strategies.find((s) => s.class_name === name)
    setForm((f) => ({ ...f, strategy_name: name, parameters: defaultParams(meta) }))
  }

  function handleParamChange(key: string, raw: string) {
    const val = raw.includes('.') ? parseFloat(raw) : parseInt(raw, 10)
    setForm((f) => ({ ...f, parameters: { ...f.parameters, [key]: isNaN(val) ? raw : val } }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setResult(null)
    run.mutate({
      ...form,
      start: startDate ? new Date(startDate).toISOString() : undefined,
      end: endDate ? new Date(endDate).toISOString() : undefined,
    })
  }

  const activeMeta = available?.strategies.find((s) => s.class_name === form.strategy_name)
  const params = activeMeta?.parameters ?? []
  const m: BacktestMetrics | null = result?.metrics ?? null
  const equityData = result?.equity_curve.map((p) => ({ time: p.timestamp, value: p.value })) ?? []

  return (
    <div className="p-6 flex flex-col gap-6 animate-fade-in">
      <h1 className="text-lg font-semibold">{t('backtests.title')}</h1>

      <div className="grid grid-cols-[320px_1fr] gap-6 items-start">
        {/* Config panel */}
        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-text-muted font-medium">{t('backtests.strategy')}</label>
            <select
              value={form.strategy_name}
              onChange={(e) => handleStrategyChange(e.target.value)}
              className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {(available?.strategies ?? []).map((s, i) => (
                <option key={s.class_name ?? `strategy-${i}`} value={s.class_name}>{s.display_name}</option>
              ))}
            </select>
            {activeMeta?.description && (
              <p className="text-[11px] text-text-muted leading-relaxed">{activeMeta.description}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('backtests.symbol')}</label>
              <select
                value={form.symbol}
                onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('backtests.timeframe')}</label>
              <select
                value={form.timeframe}
                onChange={(e) => setForm((f) => ({ ...f, timeframe: e.target.value }))}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-text-muted font-medium">
              {t('backtests.dateRange')} <span className="text-text-muted/50 font-normal">{t('backtests.optional')}</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1">
                <span className="text-[11px] text-text-muted/70">{t('backtests.startDate')}</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[11px] text-text-muted/70">{t('backtests.endDate')}</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('backtests.initialCapital')}</label>
              <input
                type="number" min={100} value={form.initial_capital}
                onChange={(e) => setForm((f) => ({ ...f, initial_capital: parseFloat(e.target.value) }))}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">
                {t('backtests.commission')} <span className="text-text-muted/60">{t('backtests.commissionSub')}</span>
              </label>
              <input
                type="number" step={0.01} min={0}
                value={+(form.commission_pct * 100).toFixed(4)}
                onChange={(e) => setForm((f) => ({ ...f, commission_pct: parseFloat(e.target.value) / 100 || 0 }))}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="e.g. 0.1"
              />
              <span className="text-[10px] text-text-muted">{t('backtests.commissionHint')}</span>
            </div>
          </div>

          {params.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('backtests.parameters')}</label>
              <div className="grid grid-cols-2 gap-2">
                {params.map((p, i) => (
                  <div key={p.key ?? `param-${i}`} className="flex flex-col gap-1">
                    <span className="text-[11px] text-text-muted">{p.label}</span>
                    <input
                      type="number" step={p.type === 'float' ? 0.1 : 1}
                      value={String(form.parameters[p.key] ?? p.default)}
                      onChange={(e) => handleParamChange(p.key, e.target.value)}
                      className="bg-background border border-border rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {run.error && (
            <p className="text-xs text-danger bg-danger/10 rounded-lg px-3 py-2">
              {(run.error as Error).message}
            </p>
          )}

          <button
            type="submit"
            disabled={!form.strategy_name || run.isPending}
            className="flex items-center justify-center gap-2 bg-primary text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            <Play size={14} />
            {run.isPending ? t('backtests.running') : t('backtests.runBacktest')}
          </button>
        </form>

        {/* Results panel */}
        <div className="flex flex-col gap-4">
          {!result && !run.isPending && (
            <div className="bg-surface border border-border rounded-xl p-12 flex flex-col items-center gap-3 text-text-muted">
              <BarChart2 size={32} strokeWidth={1} />
              <p className="text-sm">{t('backtests.emptyState')}</p>
            </div>
          )}

          {run.isPending && (
            <div className="bg-surface border border-border rounded-xl p-12 flex flex-col items-center gap-3 text-text-muted">
              <Activity size={32} strokeWidth={1} className="animate-pulse" />
              <p className="text-sm">{t('backtests.loadingState')}</p>
            </div>
          )}

          {result && m && (
            <>
              <div className="grid grid-cols-4 gap-3">
                <MetricCard label={t('backtests.metrics.totalReturn')} value={formatPercent(m.total_return_pct)} positive={m.total_return_pct >= 0} icon={m.total_return_pct >= 0 ? TrendingUp : TrendingDown} />
                <MetricCard label={t('backtests.metrics.sharpe')} value={m.sharpe_ratio.toFixed(2)} positive={m.sharpe_ratio >= 1} icon={Activity} />
                <MetricCard label={t('backtests.metrics.maxDrawdown')} value={formatPercent(m.max_drawdown_pct)} positive={false} icon={AlertTriangle} />
                <MetricCard label={t('backtests.metrics.winRate')} value={formatPercent(m.win_rate * 100)} positive={m.win_rate >= 0.5} icon={Award} />
              </div>

              <div className="grid grid-cols-4 gap-3">
                <MetricCard label={t('backtests.metrics.totalTrades')} value={String(m.total_trades)} positive={true} icon={BarChart2} />
                <MetricCard label={t('backtests.metrics.profitFactor')} value={m.profit_factor === Infinity ? '∞' : m.profit_factor.toFixed(2)} positive={m.profit_factor >= 1} icon={TrendingUp} />
                <MetricCard label={t('backtests.metrics.avgWin')} value={formatCurrency(m.avg_win)} positive={true} icon={TrendingUp} />
                <MetricCard label={t('backtests.metrics.avgLoss')} value={formatCurrency(m.avg_loss)} positive={false} icon={TrendingDown} />
              </div>

              <div className="bg-surface border border-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                  <span className="text-sm font-medium">{t('backtests.equityCurve')}</span>
                  <span className="text-xs text-text-muted">
                    {result.strategy_name} · {result.symbol} · {result.timeframe}
                  </span>
                </div>
                <EquityChart data={equityData} height={260} />
              </div>

              {result.trades.length > 0 && (
                <div className="bg-surface border border-border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-border">
                    <span className="text-sm font-medium">{t('backtests.tradeHistory', { count: result.trades.length })}</span>
                  </div>
                  <div className="overflow-x-auto max-h-72 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-surface">
                        <tr className="border-b border-border">
                          {(['side','entry','exit','size','pnl','pnlPct'] as const).map((k) => (
                            <th key={k} className="px-3 py-2 text-left text-text-muted font-medium">{t(`backtests.table.${k}`)}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.map((tr, i) => (
                          <tr key={`${tr.entry_time}-${tr.exit_time}-${i}`} className="border-b border-border/40 hover:bg-surface-2 transition-colors">
                            <td className={cn('px-3 py-2 font-medium uppercase', tr.side === 'long' ? 'text-success' : 'text-danger')}>{tr.side}</td>
                            <td className="px-3 py-2">{formatCurrency(tr.entry_price)}</td>
                            <td className="px-3 py-2">{formatCurrency(tr.exit_price)}</td>
                            <td className="px-3 py-2">{tr.size.toFixed(6)}</td>
                            <td className={cn('px-3 py-2 font-medium', tr.pnl >= 0 ? 'text-success' : 'text-danger')}>{formatCurrency(tr.pnl)}</td>
                            <td className={cn('px-3 py-2', tr.pnl_pct >= 0 ? 'text-success' : 'text-danger')}>{formatPercent(tr.pnl_pct)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, positive, icon: Icon }: {
  label: string; value: string; positive: boolean; icon: React.ElementType
}) {
  return (
    <div className="bg-surface border border-border rounded-xl p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] text-text-muted font-medium">{label}</span>
        <Icon size={12} className="text-text-muted" strokeWidth={1.5} />
      </div>
      <p className={cn('text-base font-bold', positive ? 'text-success' : 'text-danger')}>{value}</p>
    </div>
  )
}
