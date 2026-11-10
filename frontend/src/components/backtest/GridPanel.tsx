import { useTranslation } from 'react-i18next'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import type { GridArmResult, GridResponse } from '@/types/backtest'

// Preferred display order + colors. Only arms actually present in the response are rendered,
// so adding or removing a backend arm doesn't break the panel.
const ARM_ORDER = ['grid_guarded_reanchor', 'grid_accumulate_nostop'] as const
const ARM_COLOR: Record<string, string> = {
  grid_guarded_reanchor: '#2563EB',
  grid_accumulate_nostop: '#f59e0b',
}

// Metrics are ROWS and arms are COLUMNS: 2 arms x 13 metrics doesn't fit the other way round.
type Fmt = (v: number) => string
const money: Fmt = (v) => formatCurrency(v)
const pct: Fmt = (v) => `${v.toFixed(2)}%`
const num: Fmt = (v) => v.toFixed(2)
const int: Fmt = (v) => String(v)

const METRIC_ROWS: { key: keyof GridArmResult; fmt: Fmt }[] = [
  { key: 'final_equity', fmt: money },
  { key: 'total_return_pct', fmt: (v) => formatPercent(v) },
  { key: 'grid_trades', fmt: int },
  { key: 'avg_profit_per_grid_pct', fmt: (v) => `${v.toFixed(3)}%` },
  { key: 'forced_exit_pnl', fmt: money },
  { key: 'force_close_count', fmt: int },
  { key: 'max_drawdown_pct', fmt: pct },
  { key: 'sharpe_ratio', fmt: num },
  { key: 'fill_rate', fmt: pct },
  { key: 'time_in_grid_pct', fmt: pct },
  { key: 'max_inventory_notional', fmt: money },
  { key: 'worst_unrealized_pct', fmt: pct },
  { key: 'time_underwater_pct', fmt: pct },
]

export function GridPanel({ result }: { result: GridResponse }) {
  const { t } = useTranslation()

  const arms = ARM_ORDER.filter((name) => result.arms[name])

  // Merge the arms' equity curves into one dataset keyed by timestamp for an overlaid chart.
  const byTs = new Map<number, Record<string, number>>()
  for (const name of arms) {
    for (const p of result.arms[name]?.equity_curve ?? []) {
      const row = byTs.get(p.timestamp) ?? { time: Math.floor(p.timestamp / 1000) }
      row[name] = p.value
      byTs.set(p.timestamp, row)
    }
  }
  const chartData = [...byTs.values()].sort((a, b) => a.time - b.time)

  return (
    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <span className="text-sm font-medium">{t('backtests.grid.title')}</span>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* Mandatory disclosure: short legs don't model perp funding. */}
        <p className="text-xs text-warning bg-warning/10 rounded-lg px-3 py-2">
          {result.funding_rate_caveat}
        </p>
        <p className="text-xs text-text-muted">{t('backtests.grid.note')}</p>

        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fill: '#64748B', fontSize: 10 }}
              tickFormatter={(ts) =>
                new Date((ts as number) * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })
              }
              axisLine={{ stroke: '#1E293B' }}
              tickLine={false}
              minTickGap={60}
            />
            <YAxis
              tickFormatter={(v) => formatCurrency(v as number, 0)}
              tick={{ fill: '#64748B', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={64}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#16161f', border: '1px solid #1E293B', borderRadius: 8,
                color: '#f1f5f9', fontSize: 12,
              }}
              labelFormatter={(ts) => new Date((ts as number) * 1000).toLocaleString()}
              formatter={(v, n) => [formatCurrency(Number(v)), t(`backtests.grid.arm.${n}`)]}
            />
            {arms.map((name) => (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={ARM_COLOR[name]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>

        {/* Return attribution — the design's central honesty guarantee. Most grid-bot "profit"
            is inventory beta, so realized grid income is shown separately from mark-to-market
            rather than blended into a single return figure. */}
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">{t('backtests.grid.attribution')}</span>
          <p className="text-xs text-text-muted">{t('backtests.grid.attributionHint')}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {arms.map((name) => {
              const a = result.arms[name]!
              return (
                <div key={name} className="border border-border rounded-lg p-3 flex flex-col gap-1.5">
                  <span className="text-xs font-medium flex items-center gap-2">
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ background: ARM_COLOR[name] }}
                    />
                    {t(`backtests.grid.arm.${name}`)}
                  </span>
                  <span className="text-[11px] text-text-muted">{t(`backtests.grid.armHint.${name}`)}</span>
                  <div className="flex justify-between text-xs mt-1">
                    <span className="text-text-muted">{t('backtests.grid.gridIncome')}</span>
                    <span className="tabular-nums text-success">{formatCurrency(a.grid_realized_pnl)}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-text-muted">{t('backtests.grid.markToMarket')}</span>
                    <span
                      className={`tabular-nums ${a.mark_to_market_pnl < 0 ? 'text-danger' : 'text-success'}`}
                    >
                      {formatCurrency(a.mark_to_market_pnl)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-muted text-xs">
                <th className="text-left font-medium py-1">{t('backtests.grid.metric.label')}</th>
                {arms.map((name) => (
                  <th key={name} className="text-right font-medium">
                    {t(`backtests.grid.arm.${name}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRIC_ROWS.map(({ key, fmt }) => (
                <tr key={key} className="border-t border-border">
                  <td className="py-1.5">{t(`backtests.grid.metric.${key}`)}</td>
                  {arms.map((name) => (
                    <td key={name} className="text-right tabular-nums">
                      {fmt(result.arms[name]![key] as number)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  )
}
