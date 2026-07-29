import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { formatPercent } from '@/lib/utils'
import type { MonteCarloResponse, MonteCarloMethodResult } from '@/types/backtest'

interface Props {
  result: MonteCarloResponse
}

/** Drawdowns are magnitudes — show them plain (no leading + sign). */
function ddPct(v: number): string {
  return `${v.toFixed(2)}%`
}

function probPct(v: number): string {
  return `${Math.round(v * 100)}%`
}

function histogramData(method: MonteCarloMethodResult) {
  const { edges, counts } = method.histogram
  return counts.map((count, i) => ({
    mid: (edges[i] + edges[i + 1]) / 2,
    count,
  }))
}

export function MonteCarloPanel({ result }: Props) {
  const { t } = useTranslation()
  const methodNames = Object.keys(result.methods)
  const [active, setActive] = useState(methodNames[0])
  const method = result.methods[active] ?? result.methods[methodNames[0]]

  const bars = histogramData(method)

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between flex-wrap gap-2">
        <div className="flex flex-col">
          <span className="text-sm font-medium">{t('backtests.montecarlo.title')}</span>
          <span className="text-xs text-text-muted">
            {t('backtests.montecarlo.subtitle', { sims: result.n_simulations, trades: result.n_trades })}
          </span>
        </div>

        {/* Method toggle */}
        <div className="flex items-center gap-1 bg-background border border-border rounded-lg p-0.5">
          {methodNames.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setActive(name)}
              className={`px-3 py-1 text-xs rounded-md transition-colors cursor-pointer ${
                name === active ? 'bg-primary text-white' : 'text-text-muted hover:text-text'
              }`}
            >
              {t(`backtests.montecarlo.method.${name}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 flex flex-col gap-4">
        <p className="text-[11px] text-text-muted leading-relaxed">
          {t(`backtests.montecarlo.desc.${active}`)}
        </p>

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <Stat label={t('backtests.montecarlo.medianReturn')} value={formatPercent(method.total_return_pct.p50)} />
          <Stat label={t('backtests.montecarlo.p5Return')} value={formatPercent(method.total_return_pct.p5)} />
          <Stat label={t('backtests.montecarlo.medianDrawdown')} value={ddPct(method.max_drawdown_pct.p50)} />
          <Stat label={t('backtests.montecarlo.p95Drawdown')} value={ddPct(method.max_drawdown_pct.p95)} />
          <Stat label={t('backtests.montecarlo.probProfit')} value={probPct(method.prob_profit)} />
        </div>

        {method.risk_of_ruin > 0 && (
          <p className="text-xs text-danger bg-danger/10 rounded-lg px-3 py-2">
            {t('backtests.montecarlo.ruinWarning', { pct: probPct(method.risk_of_ruin) })}
          </p>
        )}

        {/* Distribution histogram of total return % */}
        <div>
          <div className="text-xs text-text-muted mb-1">{t('backtests.montecarlo.histogramTitle')}</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={bars} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
              <XAxis
                dataKey="mid"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={(v) => `${(v as number).toFixed(0)}%`}
                tick={{ fill: '#64748B', fontSize: 10 }}
                axisLine={{ stroke: '#1E293B' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#64748B', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={40}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#16161f',
                  border: '1px solid #1E293B',
                  borderRadius: '8px',
                  color: '#f1f5f9',
                  fontSize: 12,
                }}
                labelFormatter={(v) => `${Number(v).toFixed(1)}%`}
                formatter={(value) => [String(value), t('backtests.montecarlo.simsLabel')]}
              />
              <ReferenceLine
                x={result.realized_total_return_pct}
                stroke="#f59e0b"
                strokeDasharray="4 3"
                label={{ value: t('backtests.montecarlo.realized'), fill: '#f59e0b', fontSize: 10, position: 'top' }}
              />
              <Bar dataKey="count" isAnimationActive={false}>
                {bars.map((b, i) => (
                  <Cell key={i} fill={b.mid < 0 ? '#ef4444' : '#2563EB'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-background border border-border rounded-lg px-3 py-2 flex flex-col gap-0.5">
      <span className="text-[10px] text-text-muted leading-tight">{label}</span>
      <span className="text-sm font-semibold tabular-nums">{value}</span>
    </div>
  )
}
