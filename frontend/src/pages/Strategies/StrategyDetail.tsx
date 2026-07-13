import { useEffect, useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'

import { api } from '@/lib/api'
import { tradingWS } from '@/lib/websocket'
import { TradingChart } from '@/components/charts/TradingChart'
import { IndicatorControls } from '@/components/charts/IndicatorControls'
import { StatusBadge } from '@/components/strategy/StatusBadge'
import { defaultIndicatorSettings, type IndicatorSettings } from '@/lib/indicatorConfig'
import { buildStrategyMarkers, type LatestSignal } from '@/lib/strategyMarkers'
import type { StrategyInstance } from '@/types'

const fmt = (n: number | null) =>
  n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 2 })

export function StrategyDetail() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [settings, setSettings] = useState<IndicatorSettings>(defaultIndicatorSettings)
  const [showSignals, setShowSignals] = useState(false)
  const [latestSignal, setLatestSignal] = useState<LatestSignal | null>(null)

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

      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold text-text">{strategy.label}</span>
        <StatusBadge status={strategy.status} />
        <span className="text-[11px] text-text-muted font-mono">
          {strategy.symbol} · {strategy.timeframe} · {strategy.class_name}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <IndicatorControls settings={settings} onChange={setSettings} />
        <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
          <input type="checkbox" checked={showSignals} onChange={(e) => setShowSignals(e.target.checked)} />
          {t('strategies.detail.showSignals')}
        </label>
      </div>

      <div className="bg-surface border border-border rounded-xl p-2">
        <TradingChart candles={candles} settings={settings} markers={markers} height={440} />
      </div>

      <section className="space-y-2">
        <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
          {t('strategies.detail.orderHistory')}
        </h2>
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
                {orders.map((o) => (
                  <tr key={o.id} className="border-b border-border/50">
                    <td className="px-3 py-2 text-text-muted">{new Date(o.created_at).toLocaleString()}</td>
                    <td className={`px-3 py-2 ${o.side === 'buy' ? 'text-success' : o.side === 'sell' ? 'text-danger' : 'text-text-muted'}`}>{o.side ?? '—'}</td>
                    <td className="px-3 py-2 text-right">{fmt(o.filled_qty ?? o.quantity)}</td>
                    <td className="px-3 py-2 text-right">{fmt(o.avg_price)}</td>
                    <td className={`px-3 py-2 text-right ${(o.realized_pnl ?? 0) > 0 ? 'text-success' : (o.realized_pnl ?? 0) < 0 ? 'text-danger' : ''}`}>{fmt(o.realized_pnl)}</td>
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
