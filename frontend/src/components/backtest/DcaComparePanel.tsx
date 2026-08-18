import { useTranslation } from 'react-i18next'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { formatCurrency, formatPercent } from '@/lib/utils'
import type { DcaCompareResponse } from '@/types/backtest'

// Preferred display order + colors. The chart/table render only the arms actually present in
// the response, so adding or removing a backend arm doesn't break the panel.
const ARM_ORDER = [
  'dca_flat', 'dca_dip_weighted_cycle', 'cycle_buydip_selltop', 'cycle_ath_trim_rebuy',
  'dip_deploy_trim', 'cycle_selltop_redeploy_manual', 'cycle_selltop_redeploy_auto',
] as const
const ARM_COLOR: Record<string, string> = {
  dca_flat: '#64748B', dca_dip_weighted_cycle: '#2563EB', cycle_buydip_selltop: '#f59e0b',
  cycle_ath_trim_rebuy: '#a855f7', dip_deploy_trim: '#10b981',
  cycle_selltop_redeploy_manual: '#ec4899', cycle_selltop_redeploy_auto: '#06b6d4',
}

export function DcaComparePanel({ result }: { result: DcaCompareResponse }) {
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
    <div className="bg-surface border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <span className="text-sm font-medium">{t('backtests.dca.title')}</span>
      </div>

      <div className="p-4 flex flex-col gap-4">
        <p className="text-xs text-warning bg-warning/10 rounded-lg px-3 py-2">{result.caveat}</p>

        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fill: '#64748B', fontSize: 10 }}
              tickFormatter={(ts) =>
                new Date((ts as number) * 1000).toLocaleDateString([], { month: 'short', year: '2-digit' })
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
              labelFormatter={(ts) => new Date((ts as number) * 1000).toLocaleDateString()}
              formatter={(v, n) => [formatCurrency(Number(v)), t(`backtests.dca.arm.${n}`)]}
            />
            {result.cycle_markers.map((m, i) => (
              <ReferenceLine
                key={i}
                x={Math.floor(m.timestamp / 1000)}
                stroke={m.kind === 'top' ? '#ef4444' : '#22c55e'}
                strokeDasharray="4 3"
              />
            ))}
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

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-muted text-xs">
                <th className="text-left font-medium py-1">{t('backtests.dca.arm.label')}</th>
                <th className="text-right font-medium">{t('backtests.dca.finalValue')}</th>
                <th className="text-right font-medium">{t('backtests.dca.totalReturn')}</th>
                <th className="text-right font-medium">{t('backtests.dca.maxDrawdown')}</th>
                <th className="text-right font-medium">{t('backtests.dca.sharpe')}</th>
                <th className="text-right font-medium">{t('backtests.dca.avgCost')}</th>
                <th className="text-right font-medium">{t('backtests.dca.dryPowder')}</th>
              </tr>
            </thead>
            <tbody>
              {arms.map((name) => {
                const a = result.arms[name]
                if (!a) return null
                return (
                  <tr key={name} className="border-t border-border">
                    <td className="py-1.5 flex items-center gap-2">
                      <span className="inline-block w-2 h-2 rounded-full" style={{ background: ARM_COLOR[name] }} />
                      {t(`backtests.dca.arm.${name}`)}
                    </td>
                    <td className="text-right tabular-nums">{formatCurrency(a.final_value)}</td>
                    <td className="text-right tabular-nums">{formatPercent(a.total_return_pct)}</td>
                    <td className="text-right tabular-nums">{a.max_drawdown_pct.toFixed(2)}%</td>
                    <td className="text-right tabular-nums">{a.sharpe_ratio.toFixed(2)}</td>
                    <td className="text-right tabular-nums">{formatCurrency(a.avg_cost_basis)}</td>
                    <td className="text-right tabular-nums">{formatCurrency(a.dry_powder)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
