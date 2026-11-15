import { useTranslation } from 'react-i18next'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import type { WalkForwardResponse } from '@/types/backtest'

interface Props {
  result: WalkForwardResponse
}

/** The project's gate-3 bar (TODO.md 🚦 Step 5b): all three must hold. */
export function passesBar(r: WalkForwardResponse): boolean {
  const ratio = (ret: number, dd: number) => (dd > 0 ? ret / dd : ret > 0 ? Infinity : -Infinity)
  return (
    ratio(r.oos_total_return_pct, r.oos_max_drawdown_pct) >
      ratio(r.buy_hold_total_return_pct, r.buy_hold_max_drawdown_pct) &&
    r.pct_folds_profitable > 50 &&
    r.oos_sharpe >= 0.5
  )
}

function day(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10)
}

function chartData(r: WalkForwardResponse) {
  const bh = new Map(r.buy_hold_curve.map((p) => [p.timestamp, p.value]))
  return r.equity_curve.map((p) => ({ time: p.timestamp, strategy: p.value, buyHold: bh.get(p.timestamp) }))
}

export function WalkForwardPanel({ result: r }: Props) {
  const { t } = useTranslation()
  const pass = passesBar(r)

  return (
    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex flex-col gap-0.5">
        <span className="text-sm font-medium">{t('backtests.walkForward.title')}</span>
        <span className="text-xs text-text-muted">
          {t('backtests.walkForward.subtitle', {
            folds: r.folds.length, combos: r.combinations, train: r.train_bars, test: r.test_bars,
          })}
        </span>
      </div>

      <div className="p-4 flex flex-col gap-4">
        <div
          className={`text-xs rounded-lg px-3 py-2 border ${
            pass ? 'border-success/40 text-success bg-success/5' : 'border-danger/40 text-danger bg-danger/5'
          }`}
        >
          {t(pass ? 'backtests.walkForward.pass' : 'backtests.walkForward.fail')}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <Stat label={t('backtests.walkForward.oosReturn')} value={formatPercent(r.oos_total_return_pct)}
            sub={`${t('backtests.walkForward.buyHold')} ${formatPercent(r.buy_hold_total_return_pct)}`} />
          <Stat label={t('backtests.walkForward.oosDrawdown')} value={`${r.oos_max_drawdown_pct.toFixed(1)}%`}
            sub={`${t('backtests.walkForward.buyHold')} ${r.buy_hold_max_drawdown_pct.toFixed(1)}%`} />
          <Stat label={t('backtests.walkForward.oosSharpe')} value={r.oos_sharpe.toFixed(2)}
            sub={`${t('backtests.walkForward.inSample')} ${r.avg_is_score.toFixed(2)}`} />
          <Stat label={t('backtests.walkForward.foldsProfitable')} value={`${Math.round(r.pct_folds_profitable)}%`}
            sub={`${r.folds.length} ${t('backtests.walkForward.folds')}`} />
          <Stat label={t('backtests.walkForward.paramSets')} value={`${r.distinct_param_sets} / ${r.folds.length}`}
            sub={t('backtests.walkForward.paramSetsHint')} />
        </div>

        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData(r)} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis dataKey="time" tickFormatter={(ms) => day(ms as number).slice(0, 7)}
              tick={{ fill: '#64748B', fontSize: 10 }} axisLine={{ stroke: '#1E293B' }} tickLine={false} minTickGap={60} />
            <YAxis scale="log" domain={['auto', 'auto']} tickFormatter={(v) => formatCurrency(v as number)}
              tick={{ fill: '#64748B', fontSize: 10 }} axisLine={false} tickLine={false} width={72} />
            <Tooltip labelFormatter={(ms) => day(ms as number)} formatter={(v) => formatCurrency(v as number)}
              contentStyle={{ backgroundColor: '#16161f', border: '1px solid #1E293B', borderRadius: '8px', fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="strategy" name={t('backtests.walkForward.strategyLine')}
              stroke="#6366f1" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            <Line type="monotone" dataKey="buyHold" name={t('backtests.walkForward.buyHold')}
              stroke="#64748B" dot={false} strokeWidth={1} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-text-muted">
              <tr className="text-left">
                <th className="py-1.5 pr-3 font-medium">{t('backtests.walkForward.testWindow')}</th>
                <th className="py-1.5 pr-3 font-medium">{t('backtests.walkForward.chosenParams')}</th>
                <th className="py-1.5 pr-3 font-medium text-right">{t('backtests.walkForward.inSample')}</th>
                <th className="py-1.5 pr-3 font-medium text-right">{t('backtests.walkForward.oosReturn')}</th>
                <th className="py-1.5 pr-3 font-medium text-right">{t('backtests.walkForward.buyHold')}</th>
                <th className="py-1.5 font-medium text-right">{t('backtests.walkForward.trades')}</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {r.folds.map((f) => (
                <tr key={f.test_start} className="border-t border-border">
                  <td className="py-1.5 pr-3 whitespace-nowrap">{day(f.test_start)} → {day(f.test_end)}</td>
                  <td className="py-1.5 pr-3 whitespace-nowrap">
                    {Object.entries(f.params).map(([k, v]) => `${k}=${v}`).join(' ')}
                  </td>
                  <td className="py-1.5 pr-3 text-right">{f.is_score.toFixed(2)}</td>
                  <td className={`py-1.5 pr-3 text-right ${f.oos_return_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                    {formatPercent(f.oos_return_pct)}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-text-muted">{formatPercent(f.buy_hold_return_pct)}</td>
                  <td className="py-1.5 text-right">{f.oos_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-[11px] text-text-muted leading-relaxed">{r.caveat}</p>
      </div>
    </Card>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="bg-background border border-border rounded-lg px-3 py-2">
      <div className="text-[10px] text-text-muted">{label}</div>
      <div className="text-sm font-mono">{value}</div>
      <div className="text-[10px] text-text-muted">{sub}</div>
    </div>
  )
}
