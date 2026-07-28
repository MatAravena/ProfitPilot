import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Play, Sparkles, TrendingUp, TrendingDown, Activity,
  BarChart2, Award, AlertTriangle, Copy, Check,
} from 'lucide-react'
import Editor from '@monaco-editor/react'
import type { OnMount } from '@monaco-editor/react'
import { api } from '@/lib/api'
import { friendlyError } from '@/lib/errors'
import { useToastStore } from '@/stores/toast'
import type { BacktestResponse, BacktestMetrics } from '@/types/backtest'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import { EquityChart } from '@/components/charts/EquityChart'

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'] as const
const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT']

const STARTER_CODE = `class MyStrategy(StrategyBase):
    """Simple SMA crossover — replace with your own logic."""

    def generate_signals(self, data):
        closes = [b.close for b in data.bars]
        fast = self.get_param('fast', 10)
        slow = self.get_param('slow', 30)

        if len(closes) < slow + 1:
            return []

        fast_sma = sum(closes[-fast:]) / fast
        slow_sma = sum(closes[-slow:]) / slow
        prev_fast = sum(closes[-fast-1:-1]) / fast
        prev_slow = sum(closes[-slow-1:-1]) / slow

        if prev_fast <= prev_slow and fast_sma > slow_sma:
            return [signal(LONG)]
        if prev_fast >= prev_slow and fast_sma < slow_sma:
            return [signal(CLOSE)]
        return []
`

export function Builder() {
  const { t } = useTranslation()
  const [code, setCode] = useState(STARTER_CODE)
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState<string>('1d')
  const [capital, setCapital] = useState(10000)
  const [commission, setCommission] = useState(0.1)
  const [description, setDescription] = useState('')
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [aiExplanation, setAiExplanation] = useState('')
  const [copied, setCopied] = useState(false)

  const handleEditorMount: OnMount = (_editor, monaco) => {
    monaco.editor.defineTheme('profitpilot-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#0d0d14',
        'editor.lineHighlightBackground': '#ffffff06',
        'editorLineNumber.foreground': '#ffffff22',
        'editorLineNumber.activeForeground': '#ffffff50',
        'editorIndentGuide.background1': '#ffffff10',
        'editorCursor.foreground': '#2563eb',
        'editor.selectionBackground': '#2563eb33',
      },
    })
    monaco.editor.setTheme('profitpilot-dark')
  }

  const toastError = useToastStore((s) => s.error)

  const runMutation = useMutation({
    mutationFn: () => api.builder.run({ code, symbol, timeframe, initial_capital: capital, commission_pct: commission / 100 }),
    onSuccess: (data) => setResult(data),
    onError: (err) => toastError(err),
  })

  const generateMutation = useMutation({
    mutationFn: () => api.builder.generate({ description, symbol, timeframe }),
    onSuccess: (data) => { setCode(data.code); setAiExplanation(data.explanation) },
    onError: (err) => toastError(err),
  })

  function handleCopy() {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const m: BacktestMetrics | null = result?.metrics ?? null
  const equityData = result?.equity_curve.map((p) => ({ time: p.timestamp, value: p.value })) ?? []

  return (
    <div className="p-6 flex flex-col gap-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t('builder.title')}</h1>
        <span className="text-xs text-text-muted bg-surface border border-border rounded-full px-3 py-1">
          {t('builder.badge')}
        </span>
      </div>

      <div className="grid grid-cols-[1fr_340px] gap-6 items-start">
        {/* Left: code editor */}
        <div className="flex flex-col gap-4">
          {/* AI generation bar */}
          <div className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Sparkles size={13} className="text-primary" />
              <span className="text-sm font-medium">{t('builder.ai.title')}</span>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={t('builder.ai.placeholder')}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && description && generateMutation.mutate()}
                className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                onClick={() => generateMutation.mutate()}
                disabled={!description || generateMutation.isPending}
                className="flex items-center gap-1.5 bg-primary text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer shrink-0"
              >
                <Sparkles size={13} />
                {generateMutation.isPending ? t('builder.ai.generating') : t('builder.ai.generate')}
              </button>
            </div>
            {generateMutation.error && (
              <p className="text-xs text-danger">{friendlyError(generateMutation.error)}</p>
            )}
            {aiExplanation && (
              <p className="text-[11px] text-text-muted border-l-2 border-primary/40 pl-2">{aiExplanation}</p>
            )}
          </div>

          {/* Code editor */}
          <div className="bg-surface border border-border rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-muted">strategy.py</span>
                <span className="text-[10px] text-text-muted/60 bg-surface-2 px-1.5 py-0.5 rounded">sandbox</span>
              </div>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text transition-colors cursor-pointer"
              >
                {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
                {copied ? t('builder.editor.copied') : t('builder.editor.copy')}
              </button>
            </div>
            <Editor
              height="400px"
              language="python"
              value={code}
              onChange={(val) => setCode(val ?? '')}
              onMount={handleEditorMount}
              options={{
                fontSize: 12,
                fontFamily: '"JetBrains Mono", "Fira Code", Menlo, monospace',
                fontLigatures: true,
                minimap: { enabled: false },
                lineNumbers: 'on',
                tabSize: 4,
                insertSpaces: true,
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                padding: { top: 12, bottom: 12 },
                automaticLayout: true,
                renderLineHighlight: 'gutter',
                scrollbar: { verticalScrollbarSize: 4, horizontalScrollbarSize: 4 },
                overviewRulerLanes: 0,
              }}
            />
          </div>

          {runMutation.error && (
            <p className="text-xs text-danger bg-danger/10 rounded-lg px-4 py-2.5">
              {friendlyError(runMutation.error)}
            </p>
          )}
        </div>

        {/* Right: config + results */}
        <div className="flex flex-col gap-4">
          <div className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-3">
            <span className="text-xs font-medium text-text-muted">{t('builder.config.title')}</span>

            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-text-muted">{t('builder.config.symbol')}</label>
              <select
                value={symbol} onChange={(e) => setSymbol(e.target.value)}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {SYMBOLS.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-text-muted">{t('builder.config.timeframe')}</label>
              <div className="flex flex-wrap gap-1">
                {TIMEFRAMES.map((tf) => (
                  <button
                    key={tf} onClick={() => setTimeframe(tf)}
                    className={cn(
                      'px-2.5 py-1 text-xs rounded font-medium transition-colors cursor-pointer',
                      timeframe === tf ? 'bg-primary text-white' : 'bg-surface-2 text-text-muted hover:text-text',
                    )}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1">
                <label className="text-[11px] text-text-muted">{t('builder.config.capital')}</label>
                <input
                  type="number" min={100} value={capital}
                  onChange={(e) => setCapital(parseFloat(e.target.value) || 10000)}
                  className="bg-background border border-border rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[11px] text-text-muted">{t('builder.config.commission')}</label>
                <input
                  type="number" min={0} step={0.01} value={commission}
                  onChange={(e) => setCommission(parseFloat(e.target.value) || 0)}
                  className="bg-background border border-border rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            <button
              onClick={() => runMutation.mutate()}
              disabled={!code.trim() || runMutation.isPending}
              className="flex items-center justify-center gap-2 bg-primary text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <Play size={13} />
              {runMutation.isPending ? t('builder.running') : t('builder.run')}
            </button>
          </div>

          {m && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <MetricCard label={t('builder.metrics.totalReturn')} value={formatPercent(m.total_return_pct)} positive={m.total_return_pct >= 0} icon={m.total_return_pct >= 0 ? TrendingUp : TrendingDown} />
                <MetricCard label={t('builder.metrics.sharpe')} value={m.sharpe_ratio.toFixed(2)} positive={m.sharpe_ratio >= 1} icon={Activity} />
                <MetricCard label={t('builder.metrics.maxDd')} value={formatPercent(m.max_drawdown_pct)} positive={false} icon={AlertTriangle} />
                <MetricCard label={t('builder.metrics.winRate')} value={formatPercent(m.win_rate * 100)} positive={m.win_rate >= 0.5} icon={Award} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <MetricCard label={t('builder.metrics.trades')} value={String(m.total_trades)} positive={true} icon={BarChart2} />
                <MetricCard label={t('builder.metrics.profitFactor')} value={m.profit_factor == null ? '∞' : m.profit_factor.toFixed(2)} positive={m.profit_factor == null || m.profit_factor >= 1} icon={TrendingUp} />
              </div>
            </>
          )}
        </div>
      </div>

      {result && (
        <div className="flex flex-col gap-4">
          <div className="bg-surface border border-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <span className="text-sm font-medium">{t('builder.equityCurve')}</span>
              <span className="text-xs text-text-muted">{result.symbol} · {result.timeframe}</span>
            </div>
            <EquityChart data={equityData} height={240} />
          </div>

          {result.trades.length > 0 && (
            <div className="bg-surface border border-border rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <span className="text-sm font-medium">{t('builder.tradeHistory', { count: result.trades.length })}</span>
              </div>
              <div className="overflow-x-auto max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="border-b border-border">
                      {(['side','entry','exit','size','pnl','pnlPct'] as const).map((k) => (
                        <th key={k} className="px-3 py-2 text-left text-text-muted font-medium">{t(`builder.table.${k}`)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((tr, i) => (
                      <tr key={i} className="border-b border-border/40 hover:bg-surface-2 transition-colors">
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
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value, positive, icon: Icon }: {
  label: string; value: string; positive: boolean; icon: React.ElementType
}) {
  return (
    <div className="bg-surface border border-border rounded-xl p-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] text-text-muted font-medium">{label}</span>
        <Icon size={11} className="text-text-muted" strokeWidth={1.5} />
      </div>
      <p className={cn('text-sm font-bold', positive ? 'text-success' : 'text-danger')}>{value}</p>
    </div>
  )
}
