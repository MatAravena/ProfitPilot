import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Play, TrendingUp, TrendingDown, Activity, BarChart2, Award, AlertTriangle, Dices } from 'lucide-react'
import { api } from '@/lib/api'
import { friendlyError } from '@/lib/errors'
import { useToastStore } from '@/stores/toast'
import type { BacktestRequest, BacktestResponse, BacktestMetrics, StrategyMeta, MonteCarloResponse, DcaCompareResponse } from '@/types/backtest'
import type { StrategyInstance } from '@/types'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { EquityChart } from '@/components/charts/EquityChart'
import { MetricCard } from '@/components/backtest/MetricCard'
import { TradeTable } from '@/components/backtest/TradeTable'
import { BacktestChart } from '@/components/backtest/BacktestChart'
import { MonteCarloPanel } from '@/components/backtest/MonteCarloPanel'
import { DcaComparePanel } from '@/components/backtest/DcaComparePanel'

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
    slippage_pct: 0.0005,       // conservative 5 bps adverse slippage per fill
    position_size_pct: 0.02,   // same risk model as live (2% default); keeps backtest ≈ live magnitude
    parameters: {},
  })
  const [selectValue, setSelectValue] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState(new Date().toISOString().split('T')[0])
  const [result, setResult] = useState<BacktestResponse | null>(null)
  // The exact request that produced `result`, so Monte Carlo stresses the identical run.
  const [lastReq, setLastReq] = useState<BacktestRequest | null>(null)
  const [mcResult, setMcResult] = useState<MonteCarloResponse | null>(null)
  const [dcaResult, setDcaResult] = useState<DcaCompareResponse | null>(null)

  const { data: available } = useQuery({
    queryKey: ['backtests', 'strategies'],
    queryFn: api.backtests.strategies,
    staleTime: Infinity,
  })

  const { data: instances = [] } = useQuery<StrategyInstance[]>({
    queryKey: ['strategies'],
    queryFn: api.strategies.list,
  })

  const toastError = useToastStore((s) => s.error)
  const run = useMutation({
    mutationFn: (req: BacktestRequest) => api.backtests.run(req),
    onSuccess: (data) => setResult(data),
    onError: (err) => toastError(err),
  })

  // Monte Carlo is opt-in — it re-runs the backtest server-side, so we don't fold its
  // latency into every ordinary run.
  const montecarlo = useMutation({
    mutationFn: () => api.backtests.montecarlo({ ...(lastReq as BacktestRequest), n_simulations: 5000 }),
    onSuccess: (data) => setMcResult(data),
    onError: (err) => toastError(err),
  })

  // DCA vs cycle-grid comparison — BTC-focused; re-runs an accumulation sim server-side.
  const dcaCompare = useMutation({
    mutationFn: () => api.backtests.dcaCompare({
      symbol: form.symbol, timeframe: '1d',
      start: startDate ? new Date(startDate).toISOString() : undefined,
      end: endDate ? new Date(endDate).toISOString() : undefined,
      capital_model: 'contributions', contribution_amount: 100, contribution_interval_days: 7,
      commission_pct: form.commission_pct, slippage_pct: form.slippage_pct ?? 0.0005,
    }),
    onSuccess: (data) => setDcaResult(data),
    onError: (err) => toastError(err),
  })

  // Pre-fill SL/TP from the user's risk defaults (adjustable per run).
  const { data: riskProfile } = useQuery({ queryKey: ['risk-profile'], queryFn: api.settings.getRisk })

  useEffect(() => {
    if (available?.strategies.length && !form.strategy_name) {
      const first = available.strategies[0]
      setSelectValue(first.class_name)
      setForm((f) => ({ ...f, strategy_name: first.class_name, parameters: defaultParams(first) }))
    }
  }, [available])

  useEffect(() => {
    if (riskProfile && form.stop_loss_pct === undefined) {
      setForm((f) => ({
        ...f,
        stop_loss_pct: riskProfile.stop_loss_pct,
        take_profit_pct: riskProfile.take_profit_pct,
      }))
    }
  }, [riskProfile])

  function handleStrategyChange(value: string) {
    setSelectValue(value)
    if (value.startsWith('instance:')) {
      const id = value.slice('instance:'.length)
      const inst = instances.find((i) => i.id === id)
      if (!inst) return
      const meta = available?.strategies.find((s) => s.class_name === inst.class_name)
      setForm((f) => ({
        ...f,
        strategy_name: inst.class_name,
        symbol: inst.symbol,
        timeframe: inst.timeframe,
        parameters: Object.keys(inst.parameters).length ? inst.parameters as Record<string, number> : defaultParams(meta),
      }))
    } else {
      const meta = available?.strategies.find((s) => s.class_name === value)
      setForm((f) => ({ ...f, strategy_name: value, parameters: defaultParams(meta) }))
    }
  }

  function handleParamChange(key: string, raw: string) {
    const val = raw.includes('.') ? parseFloat(raw) : parseInt(raw, 10)
    setForm((f) => ({ ...f, parameters: { ...f.parameters, [key]: isNaN(val) ? raw : val } }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setResult(null)
    setMcResult(null)   // a fresh backtest invalidates the previous MC run
    setDcaResult(null)  // ...and the previous DCA comparison
    const req: BacktestRequest = {
      ...form,
      start: startDate ? new Date(startDate).toISOString() : undefined,
      end: endDate ? new Date(endDate).toISOString() : undefined,
    }
    setLastReq(req)
    run.mutate(req)
  }

  const activeMeta = available?.strategies.find((s) => s.class_name === form.strategy_name)
  const params = activeMeta?.parameters ?? []
  const m: BacktestMetrics | null = result?.metrics ?? null
  // equity_curve timestamps are Unix ms — convert to seconds for EquityChart
  const equityData = result?.equity_curve.map((p) => ({ time: Math.floor(p.timestamp / 1000), value: p.value })) ?? []

  return (
    <div className="p-6 flex flex-col gap-6 animate-fade-in">
      <h1 className="text-lg font-semibold">{t('backtests.title')}</h1>

      <div className="grid grid-cols-[320px_1fr] gap-6 items-start">
        {/* Config panel */}
        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-text-muted font-medium">{t('backtests.strategy')}</label>
            <select
              value={selectValue}
              onChange={(e) => handleStrategyChange(e.target.value)}
              className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {instances.length > 0 && (
                <optgroup label="My Strategies">
                  {instances.map((inst) => (
                    <option key={inst.id} value={`instance:${inst.id}`}>
                      {inst.label || inst.class_name} — {inst.symbol} {inst.timeframe}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Built-in">
                {(available?.strategies ?? []).map((s, i) => (
                  <option key={s.class_name ?? `strategy-${i}`} value={s.class_name}>{s.display_name}</option>
                ))}
              </optgroup>
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
                type="number" min={100} value={Number.isNaN(form.initial_capital) ? '' : form.initial_capital}
                onChange={(e) => { const n = parseFloat(e.target.value); setForm((f) => ({ ...f, initial_capital: Number.isNaN(n) ? 0 : n })) }}
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

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-text-muted font-medium">
              {t('backtests.slippage')} <span className="text-text-muted/60">{t('backtests.commissionSub')}</span>
            </label>
            <input
              type="number" step={0.01} min={0}
              value={+((form.slippage_pct ?? 0) * 100).toFixed(4)}
              onChange={(e) => setForm((f) => ({ ...f, slippage_pct: parseFloat(e.target.value) / 100 || 0 }))}
              className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="e.g. 0.05"
            />
            <span className="text-[10px] text-text-muted">{t('backtests.slippageHint')}</span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('backtests.stopLoss')}</label>
              <input
                type="text" inputMode="decimal"
                value={form.stop_loss_pct != null ? String(+(form.stop_loss_pct * 100).toFixed(4)) : ''}
                placeholder={t('backtests.none')}
                onChange={(e) => {
                  const raw = e.target.value
                  const n = raw === '' ? null : Number(raw) / 100
                  setForm((f) => ({ ...f, stop_loss_pct: raw === '' || Number.isNaN(Number(raw)) ? null : n }))
                }}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('backtests.takeProfit')}</label>
              <input
                type="text" inputMode="decimal"
                value={form.take_profit_pct != null ? String(+(form.take_profit_pct * 100).toFixed(4)) : ''}
                placeholder={t('backtests.none')}
                onChange={(e) => {
                  const raw = e.target.value
                  const n = raw === '' ? null : Number(raw) / 100
                  setForm((f) => ({ ...f, take_profit_pct: raw === '' || Number.isNaN(Number(raw)) ? null : n }))
                }}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-text-muted font-medium">{t('backtests.positionSize')}</label>
            <input
              type="text" inputMode="decimal"
              value={form.position_size_pct != null ? String(+(form.position_size_pct * 100).toFixed(4)) : ''}
              placeholder="2"
              onChange={(e) => {
                const raw = e.target.value
                const n = raw === '' || Number.isNaN(Number(raw)) ? null : Number(raw) / 100
                setForm((f) => ({ ...f, position_size_pct: n }))
              }}
              className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <span className="text-[10px] text-text-muted">{t('backtests.positionSizeHint')}</span>
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
              {friendlyError(run.error)}
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
                <MetricCard label={t('backtests.metrics.totalTrades')} 
                  value={String(m.total_trades)} positive={true} icon={BarChart2} />
                <MetricCard label={t('backtests.metrics.profitFactor')}
                  value={m.profit_factor == null ? '∞' : m.profit_factor.toFixed(2)}
                  positive={m.profit_factor == null || m.profit_factor >= 1} icon={TrendingUp} />
                <MetricCard label={t('backtests.metrics.avgWin')} value={formatCurrency(m.avg_win)} positive={true} icon={TrendingUp} />
                <MetricCard label={t('backtests.metrics.avgLoss')} value={formatCurrency(m.avg_loss)} positive={false} icon={TrendingDown} />
              </div>

              {result.prices.length > 0 && (
                <div className="bg-surface border border-border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                    <span className="text-sm font-medium">Price · Trade Entries &amp; Exits</span>
                    <span className="text-xs text-text-muted">
                      ▲ buy &nbsp; ▼ sell &nbsp;·&nbsp; scroll or drag to zoom
                    </span>
                  </div>
                  <BacktestChart
                    prices={result.prices}
                    trades={result.trades}
                    height={280}
                  />
                </div>
              )}

              <div className="bg-surface border border-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                  <span className="text-sm font-medium">{t('backtests.equityCurve')}</span>
                  <span className="text-xs text-text-muted">
                    {result.strategy_name} · {result.symbol} · {result.timeframe}
                  </span>
                </div>
                <EquityChart data={equityData} height={260} />
              </div>

              <TradeTable trades={result.trades} />

              {/* Monte Carlo — opt-in stress test of this result's trade sequence. */}
              {mcResult ? (
                <MonteCarloPanel result={mcResult} />
              ) : (
                <button
                  type="button"
                  onClick={() => montecarlo.mutate()}
                  disabled={montecarlo.isPending || !lastReq}
                  className="flex items-center justify-center gap-2 self-start bg-surface border border-border rounded-lg px-4 py-2.5 text-sm font-medium hover:border-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  <Dices size={14} />
                  {montecarlo.isPending ? t('backtests.montecarlo.running') : t('backtests.montecarlo.run')}
                </button>
              )}

              {/* DCA vs halving-cycle-grid comparison — opt-in, BTC-focused. */}
              {dcaResult ? (
                <DcaComparePanel result={dcaResult} />
              ) : (
                <button
                  type="button"
                  onClick={() => dcaCompare.mutate()}
                  disabled={dcaCompare.isPending}
                  className="flex items-center justify-center gap-2 self-start bg-surface border border-border rounded-lg px-4 py-2.5 text-sm font-medium hover:border-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  <TrendingUp size={14} />
                  {dcaCompare.isPending ? t('backtests.dca.running') : t('backtests.dca.run')}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
