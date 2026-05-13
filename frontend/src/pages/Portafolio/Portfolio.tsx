import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { TrendingUp, TrendingDown, DollarSign, Activity, ArrowUpRight, ArrowDownLeft, CheckCircle, AlertCircle } from 'lucide-react'
import { usePortfolioStore } from '@/stores/portfolio'
import { api } from '@/lib/api'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import type { PlaceOrderPayload } from '@/types'
import { EquityChart } from '@/components/charts/EquityChart'

const EMPTY_FORM: PlaceOrderPayload = {
  symbol: '',
  side: 'buy',
  order_type: 'market',
  quantity: 0,
  limit_price: undefined,
  time_in_force: 'gtc',
}

export function Portfolio() {
  const { t } = useTranslation()
  const { positions, equity, cashBalance, totalPnl } = usePortfolioStore()
  const qc = useQueryClient()

  const [form, setForm] = useState<PlaceOrderPayload>(EMPTY_FORM)
  const [successMsg, setSuccessMsg] = useState('')

  const { data: history = [] } = useQuery({
    queryKey: ['portfolio', 'history'],
    queryFn: () => api.portfolio.history(500),
    refetchInterval: 60_000,
  })

  const { data: brokers = [] } = useQuery({
    queryKey: ['brokers'],
    queryFn: api.brokers.list,
    staleTime: 30_000,
  })

  const [selectedBroker, setSelectedBroker] = useState('')
  useEffect(() => {
    if (brokers.length && !selectedBroker) setSelectedBroker(brokers[0].broker_id)
  }, [brokers])

  const placeOrder = useMutation({
    mutationFn: (payload: PlaceOrderPayload) => api.brokers.placeOrder(selectedBroker, payload),
    onSuccess: (result) => {
      setSuccessMsg(`Order ${result.broker_order_id} → ${result.status}`)
      setForm(EMPTY_FORM)
      setTimeout(() => setSuccessMsg(''), 4000)
      qc.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })

  const equityData = history.map((p) => ({
    time: Math.floor(new Date(p.snapped_at).getTime() / 1000),
    value: p.equity,
  }))

  const pnlPositive = totalPnl >= 0

  const kpis = [
    { label: t('portfolio.kpis.equity'),  value: formatCurrency(equity),      icon: DollarSign, colored: false },
    { label: t('portfolio.kpis.cash'),    value: formatCurrency(cashBalance),  icon: Activity,   colored: false },
    { label: t('portfolio.kpis.pnl'),     value: formatCurrency(totalPnl),     icon: pnlPositive ? TrendingUp : TrendingDown, colored: true, positive: pnlPositive },
  ]

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedBroker) return
    const payload: PlaceOrderPayload = {
      ...form,
      symbol: form.symbol.toUpperCase(),
      limit_price: form.order_type === 'limit' ? form.limit_price : undefined,
    }
    placeOrder.mutate(payload)
  }

  const inputCls = 'bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary w-full'

  const tableHeaders = [
    t('portfolio.table.symbol'), t('portfolio.table.broker'), t('portfolio.table.qty'),
    t('portfolio.table.entry'), t('portfolio.table.current'), t('portfolio.table.unrealizedPnl'), t('portfolio.table.pct'),
  ]

  return (
    <div className="p-6 flex flex-col gap-6 animate-fade-in">
      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-4">
        {kpis.map(({ label, value, icon: Icon, colored, positive }) => (
          <div key={label} className="bg-surface border border-border rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-text-muted font-medium">{label}</span>
              <Icon size={14} className="text-text-muted" strokeWidth={1.5} />
            </div>
            <p className={cn('text-2xl font-bold', colored && (positive ? 'text-success' : 'text-danger'))}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {/* Equity curve */}
      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-sm font-medium">{t('portfolio.equityOver')}</span>
          <span className="text-[11px] text-text-muted">{t('portfolio.snapshots', { count: history.length })}</span>
        </div>
        {history.length === 0 ? (
          <div className="px-4 py-12 text-center text-text-muted text-sm">
            <p>{t('portfolio.noHistory')}</p>
            <p className="text-xs mt-1">{t('portfolio.noHistoryHint')}</p>
          </div>
        ) : (
          <EquityChart data={equityData} height={220} />
        )}
      </div>

      {/* Open positions + Place Order */}
      <div className="grid grid-cols-[1fr_300px] gap-4 items-start">
        <div className="bg-surface border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <span className="text-sm font-medium">{t('portfolio.openPositions')}</span>
            <span className="text-xs text-text-muted">{t('portfolio.activePositions', { count: positions.length })}</span>
          </div>

          {positions.length === 0 ? (
            <div className="px-4 py-10 text-center text-text-muted text-sm">{t('portfolio.noPositions')}</div>
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
                    <td className="px-4 py-3 text-text-muted capitalize text-xs">{p.broker}</td>
                    <td className="px-4 py-3">{p.size}</td>
                    <td className="px-4 py-3">{formatCurrency(p.entryPrice)}</td>
                    <td className="px-4 py-3">{formatCurrency(p.currentPrice)}</td>
                    <td className={cn('px-4 py-3 font-medium', p.unrealizedPnl >= 0 ? 'text-success' : 'text-danger')}>
                      {formatCurrency(p.unrealizedPnl)}
                    </td>
                    <td className={cn('px-4 py-3 text-xs', p.unrealizedPnlPct >= 0 ? 'text-success' : 'text-danger')}>
                      {formatPercent(p.unrealizedPnlPct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Place Order panel */}
        <div className="bg-surface border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <span className="text-sm font-medium">{t('portfolio.placeOrder.title')}</span>
          </div>

          {brokers.length === 0 ? (
            <div className="px-4 py-8 text-center text-text-muted text-xs">
              {t('portfolio.placeOrder.noBroker')}
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="p-4 flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-[11px] text-text-muted font-medium">{t('portfolio.placeOrder.broker')}</label>
                <select value={selectedBroker} onChange={(e) => setSelectedBroker(e.target.value)} className={inputCls}>
                  {brokers.map((b) => (
                    <option key={b.id} value={b.broker_id}>
                      {b.label} {b.is_paper ? '(paper)' : '(live)'}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[11px] text-text-muted font-medium">{t('portfolio.placeOrder.symbol')}</label>
                <input
                  type="text" placeholder="BTCUSDT" value={form.symbol}
                  onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}
                  className={inputCls} required
                />
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button" onClick={() => setForm((f) => ({ ...f, side: 'buy' }))}
                  className={cn(
                    'flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-colors cursor-pointer',
                    form.side === 'buy' ? 'bg-success text-white' : 'bg-surface-2 text-text-muted hover:text-text',
                  )}
                >
                  <ArrowUpRight size={12} /> {t('portfolio.placeOrder.buy')}
                </button>
                <button
                  type="button" onClick={() => setForm((f) => ({ ...f, side: 'sell' }))}
                  className={cn(
                    'flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-colors cursor-pointer',
                    form.side === 'sell' ? 'bg-danger text-white' : 'bg-surface-2 text-text-muted hover:text-text',
                  )}
                >
                  <ArrowDownLeft size={12} /> {t('portfolio.placeOrder.sell')}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                {(['market', 'limit'] as const).map((orderT) => (
                  <button
                    key={orderT} type="button" onClick={() => setForm((f) => ({ ...f, order_type: orderT }))}
                    className={cn(
                      'py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer',
                      form.order_type === orderT
                        ? 'bg-primary/20 text-primary border border-primary/40'
                        : 'bg-surface-2 text-text-muted hover:text-text',
                    )}
                  >
                    {t(`portfolio.placeOrder.${orderT}`)}
                  </button>
                ))}
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[11px] text-text-muted font-medium">{t('portfolio.placeOrder.quantity')}</label>
                <input
                  type="number" min={0} step="any" placeholder="0.001"
                  value={form.quantity || ''}
                  onChange={(e) => setForm((f) => ({ ...f, quantity: parseFloat(e.target.value) || 0 }))}
                  className={inputCls} required
                />
              </div>

              {form.order_type === 'limit' && (
                <div className="flex flex-col gap-1">
                  <label className="text-[11px] text-text-muted font-medium">{t('portfolio.placeOrder.limitPrice')}</label>
                  <input
                    type="number" min={0} step="any" placeholder="0.00"
                    value={form.limit_price || ''}
                    onChange={(e) => setForm((f) => ({ ...f, limit_price: parseFloat(e.target.value) || undefined }))}
                    className={inputCls} required
                  />
                </div>
              )}

              {placeOrder.error && (
                <div className="flex items-center gap-1.5 text-xs text-danger bg-danger/10 rounded-lg px-3 py-2">
                  <AlertCircle size={12} />
                  {(placeOrder.error as Error).message}
                </div>
              )}

              {successMsg && (
                <div className="flex items-center gap-1.5 text-xs text-success bg-success/10 rounded-lg px-3 py-2">
                  <CheckCircle size={12} />
                  {successMsg}
                </div>
              )}

              <button
                type="submit"
                disabled={!form.symbol || !form.quantity || placeOrder.isPending}
                className={cn(
                  'w-full py-2.5 rounded-lg text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed',
                  form.side === 'buy' ? 'bg-success text-white hover:bg-success/90' : 'bg-danger text-white hover:bg-danger/90',
                )}
              >
                {placeOrder.isPending
                  ? t('portfolio.placeOrder.placing')
                  : `${form.side === 'buy' ? t('portfolio.placeOrder.buy') : t('portfolio.placeOrder.sell')} ${form.symbol || '—'}`}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
