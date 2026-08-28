import { useEffect, useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, DollarSign, Target, ListChecks, Clock, Zap } from 'lucide-react'

import { api } from '@/lib/api'
import { tradingWS } from '@/lib/websocket'
import { cn, formatCurrency, formatTimeAgo } from '@/lib/utils'
import { TradingChart } from '@/components/charts/TradingChart'
import { IndicatorControls } from '@/components/charts/IndicatorControls'
import { StatusBadge } from '@/components/strategy/StatusBadge'
import { SignalRow } from '@/components/strategy/SignalRow'
import { Switch } from '@/components/ui/Switch'
import { Card } from '@/components/ui/Card'
import { MetricCard } from '@/components/backtest/MetricCard'
import { PaginationButtons } from '@/components/ui/PaginationButtons'
import { defaultIndicatorSettings, type IndicatorSettings } from '@/lib/indicatorConfig'
import { buildStrategyMarkers, type LatestSignal } from '@/lib/strategyMarkers'
import type { StrategyInstance } from '@/types'

const fmt = (n: number | null) =>
  n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 2 })

const ORDERS_PAGE_SIZE = 8

export function StrategyDetail() {
  const { id = '' } = useParams()
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const [settings, setSettings] = useState<IndicatorSettings>(defaultIndicatorSettings)
  const [showSignals, setShowSignals] = useState(false)
  const [latestSignal, setLatestSignal] = useState<LatestSignal | null>(null)
  const [ordersPage, setOrdersPage] = useState(0)

  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'], queryFn: api.strategies.list, refetchInterval: 10_000,
  })
  const strategy: StrategyInstance | undefined = strategies.find((s) => s.id === id)

  const { data: candles = [] } = useQuery({
    queryKey: ['ohlcv', strategy?.symbol, strategy?.timeframe],
    queryFn: () => api.market.ohlcv(strategy!.symbol, strategy!.timeframe),
    enabled: !!strategy,
    refetchInterval: 20_000,
  })

  const { data: orders = [] } = useQuery({
    queryKey: ['strategy-orders', id],
    queryFn: () => api.strategies.orders(id),
    enabled: !!strategy,
    refetchInterval: 20_000,
  })

  const { data: signals = [] } = useQuery({
    queryKey: ['signals', id],
    queryFn: () => api.signals.list(200, id),
    enabled: !!strategy,
    refetchInterval: 20_000,
  })

  // Live updates: opt into the executor's broadcast channels for this session.
  // NOTE: single-detail-page-at-a-time (Phase 1); unsubscribing here is fine.
  useEffect(() => {
    if (!id) return
    tradingWS.subscribe('strategy.order')
    tradingWS.subscribe('strategy.signal')

    const offOrder = tradingWS.on('strategy.order', (data) => {
      const d = data as { strategy_id: string }
      if (d.strategy_id !== id) return
      qc.invalidateQueries({ queryKey: ['strategy-orders', id] })
    })
    const offSignal = tradingWS.on('strategy.signal', (data) => {
      const d = data as { strategy_id: string; direction: string; generated_at: string }
      if (d.strategy_id !== id) return
      setLatestSignal({
        direction: d.direction,
        time: Math.floor(new Date(d.generated_at).getTime() / 1000),
      })
    })

    return () => {
      offOrder()
      offSignal()
      tradingWS.unsubscribe('strategy.order')
      tradingWS.unsubscribe('strategy.signal')
    }
  }, [id, qc])

  const markers = useMemo(
    () => buildStrategyMarkers({ orders, signals, latestSignal, showSignals }),
    [orders, signals, latestSignal, showSignals],
  )

  const stats = useMemo(() => {
    const closed = orders.filter((o) => o.realized_pnl != null)
    const filled = orders.filter((o) => o.filled_qty != null)
    const wins = closed.filter((o) => (o.realized_pnl ?? 0) > 0).length
    const realizedPnl = closed.reduce((sum, o) => sum + (o.realized_pnl ?? 0), 0)
    const winRate = closed.length ? wins / closed.length : null
    const lastFillAt = filled.length ? filled[0].created_at : null
    return { realizedPnl, winRate, filledCount: filled.length, lastFillAt }
  }, [orders])

  const recentSignals = useMemo(
    () => [...signals].sort((a, b) => b.generated_at.localeCompare(a.generated_at)).slice(0, 8),
    [signals],
  )

  useEffect(() => { setOrdersPage(0) }, [id])
  const ordersTotal = orders.length
  const ordersFrom = ordersTotal === 0 ? 0 : ordersPage * ORDERS_PAGE_SIZE + 1
  const ordersTo = Math.min(ordersFrom + ORDERS_PAGE_SIZE - 1, ordersTotal)
  const pagedOrders = orders.slice(ordersPage * ORDERS_PAGE_SIZE, ordersPage * ORDERS_PAGE_SIZE + ORDERS_PAGE_SIZE)

  if (!strategy) {
    return (
      <div className="p-6">
        <Link to="/strategies" className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text">
          <ArrowLeft size={14} /> {t('strategies.detail.back')}
        </Link>
        <p className="mt-6 text-sm text-text-muted">{t('strategies.detail.notFound')}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-6 gap-4 overflow-y-auto">
      <Link to="/strategies" className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text">
        <ArrowLeft size={14} /> {t('strategies.detail.back')}
      </Link>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-lg font-semibold text-text">{strategy.label}</span>
        <StatusBadge status={strategy.status} />
        <span className="text-[11px] text-text-muted font-mono">
          {strategy.symbol} · {strategy.timeframe} · {strategy.class_name}
        </span>
        {strategy.last_signal_at && (
          <span className="ml-auto text-[11px] text-text-muted flex items-center gap-1">
            <Zap size={11} className="text-primary" />
            {t('strategies.detail.lastSignal', { time: formatTimeAgo(strategy.last_signal_at, i18n.language) })}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label={t('strategies.detail.stats.pnl')}
          value={formatCurrency(stats.realizedPnl)}
          positive={stats.realizedPnl >= 0}
          icon={DollarSign}
        />
        <MetricCard
          label={t('strategies.detail.stats.winRate')}
          value={stats.winRate == null ? '—' : `${Math.round(stats.winRate * 100)}%`}
          positive={stats.winRate == null || stats.winRate >= 0.5}
          icon={Target}
        />
        <MetricCard
          label={t('strategies.detail.stats.filled')}
          value={String(stats.filledCount)}
          positive
          icon={ListChecks}
        />
        <MetricCard
          label={t('strategies.detail.stats.lastFill')}
          value={stats.lastFillAt ? formatTimeAgo(stats.lastFillAt, i18n.language) : '—'}
          positive
          icon={Clock}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[200px_1fr_300px] lg:items-stretch">
        <Card className="order-2 overflow-y-auto p-3 lg:order-1 lg:max-h-[520px]">
          <IndicatorControls settings={settings} onChange={setSettings} />
        </Card>

        <Card className="order-1 p-2 lg:order-2">
          <TradingChart candles={candles} settings={settings} markers={markers} height={520} />
        </Card>

        <Card className="order-3 overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2 shrink-0">
            <Zap size={13} className="text-primary" />
            <span className="text-sm font-medium">{t('strategies.detail.signals.title')}</span>
            <div className="ml-auto">
              <Switch bare label={t('strategies.detail.showSignals')} checked={showSignals} onChange={setShowSignals} />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto lg:max-h-[476px]">
            {recentSignals.length === 0 ? (
              <div className="px-4 py-10 text-center text-text-muted text-xs">
                {t('strategies.detail.signals.empty')}
              </div>
            ) : (
              recentSignals.map((s) => <SignalRow key={s.id} s={s} />)
            )}
          </div>
        </Card>
      </div>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
            {t('strategies.detail.orderHistory')}
          </h2>
          {ordersTotal > 0 && (
            <div className="flex items-center gap-2 text-[11px] text-text-muted">
              <span className="tabular-nums">
                {t('strategies.detail.showing', { from: ordersFrom, to: ordersTo, total: ordersTotal })}
              </span>
              <PaginationButtons
                onPrev={() => setOrdersPage((p) => Math.max(0, p - 1))}
                onNext={() => setOrdersPage((p) => (ordersTo < ordersTotal ? p + 1 : p))}
                prevDisabled={ordersPage === 0}
                nextDisabled={ordersTo >= ordersTotal}
                prevLabel={t('strategies.detail.prev')}
                nextLabel={t('strategies.detail.next')}
              />
            </div>
          )}
        </div>
        {orders.length === 0 ? (
          <p className="text-sm text-text-muted">{t('strategies.detail.noOrders')}</p>
        ) : (
          <div className="overflow-x-auto border border-border rounded-lg">
            <table className="w-full text-[12px]">
              <thead className="text-text-muted">
                <tr className="border-b border-border">
                  <th className="text-left px-3 py-2 font-medium">{t('strategies.detail.colTime')}</th>
                  <th className="text-left px-3 py-2 font-medium">{t('strategies.detail.colSide')}</th>
                  <th className="text-right px-3 py-2 font-medium">{t('strategies.detail.colQty')}</th>
                  <th className="text-right px-3 py-2 font-medium">{t('strategies.detail.colPrice')}</th>
                  <th className="text-right px-3 py-2 font-medium">{t('strategies.detail.colPnl')}</th>
                  <th className="text-left px-3 py-2 font-medium">{t('strategies.detail.colStatus')}</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {pagedOrders.map((o) => (
                  <tr key={o.id} className="border-b border-border/50 hover:bg-surface-2 transition-colors">
                    <td className="px-3 py-2 text-text-muted">{new Date(o.created_at).toLocaleString()}</td>
                    <td className={cn('px-3 py-2', o.side === 'buy' ? 'text-success' : o.side === 'sell' ? 'text-danger' : 'text-text-muted')}>{o.side ?? '—'}</td>
                    <td className="px-3 py-2 text-right">{fmt(o.filled_qty ?? o.quantity)}</td>
                    <td className="px-3 py-2 text-right">{fmt(o.avg_price)}</td>
                    <td className={cn('px-3 py-2 text-right', (o.realized_pnl ?? 0) > 0 ? 'text-success' : (o.realized_pnl ?? 0) < 0 ? 'text-danger' : '')}>{fmt(o.realized_pnl)}</td>
                    <td className="px-3 py-2 text-text-muted">{o.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
