import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '@/lib/api'
import { TradingChart, type CrosshairSnapshot } from '@/components/charts/TradingChart'
import { IndicatorControls } from '@/components/charts/IndicatorControls'
import { ChartMetricsPanel } from '@/components/charts/ChartMetricsPanel'
import {
  defaultIndicatorSettings, type IndicatorSettings,
} from '@/lib/indicatorConfig'

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d', '1w'] as const
const QUICK_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT']
const STORAGE_KEY = 'pp.trade.indicators'

function loadSettings(): IndicatorSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as Partial<IndicatorSettings>
      // Merge over defaults so newly added indicators always appear.
      return { ...defaultIndicatorSettings(), ...saved }
    }
  } catch { /* ignore */ }
  return defaultIndicatorSettings()
}

export function Trade() {
  const { t } = useTranslation()
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [symbolInput, setSymbolInput] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>('1h')
  const [settings, setSettings] = useState<IndicatorSettings>(loadSettings)
  const [hover, setHover] = useState<CrosshairSnapshot | null>(null)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  }, [settings])

  const { data: candles = [], isFetching, isError } = useQuery({
    queryKey: ['ohlcv', symbol, timeframe, 'trade'],
    queryFn: () => api.market.ohlcv(symbol, timeframe, 500),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })

  const { data: portfolio } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: () => api.portfolio.summary(),
    refetchInterval: 30_000,
  })

  const position = useMemo(
    () => portfolio?.positions.find((p) => p.symbol.toUpperCase() === symbol.toUpperCase()),
    [portfolio, symbol],
  )

  function applySymbol() {
    const s = symbolInput.trim().toUpperCase()
    if (s) setSymbol(s)
  }

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5">
          <input
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && applySymbol()}
            placeholder="Symbol"
            className="w-32 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-mono text-text focus:border-primary focus:outline-none"
          />
          <button
            onClick={applySymbol}
            className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 cursor-pointer"
          >
            {t('trade.load')}
          </button>
        </div>

        <div className="flex gap-1">
          {QUICK_SYMBOLS.map((s) => (
            <button
              key={s}
              onClick={() => { setSymbol(s); setSymbolInput(s) }}
              className={`rounded-md px-2 py-1 text-[11px] font-medium cursor-pointer transition-colors ${
                symbol === s ? 'bg-primary/15 text-primary' : 'text-text-muted hover:text-text hover:bg-surface-2'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="ml-auto flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium cursor-pointer transition-colors ${
                timeframe === tf ? 'bg-primary/15 text-primary' : 'text-text-muted hover:text-text hover:bg-surface-2'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Main grid: controls | chart | metrics */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[200px_1fr_240px]">
        {/* Indicator controls */}
        <div className="order-2 overflow-y-auto rounded-xl border border-border bg-surface p-3 lg:order-1">
          <IndicatorControls settings={settings} onChange={setSettings} />
        </div>

        {/* Chart */}
        <div className="order-1 relative min-h-[460px] rounded-xl border border-border bg-surface p-3 lg:order-2">
          {isFetching && (
            <div className="absolute right-4 top-4 z-10 flex items-center gap-1">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
              <span className="text-[10px] font-medium text-success">LIVE</span>
            </div>
          )}
          {isError ? (
            <div className="flex h-full items-center justify-center text-sm text-danger">
              {t('trade.loadError', { symbol })}
            </div>
          ) : candles.length ? (
            <TradingChart candles={candles} settings={settings} onHover={setHover} height={520} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-text-muted">
              {t('trade.loading')}
            </div>
          )}
        </div>

        {/* Metrics */}
        <div className="order-3 overflow-y-auto rounded-xl border border-border bg-surface p-3">
          <ChartMetricsPanel symbol={symbol} candles={candles} hover={hover} position={position} />
        </div>
      </div>
    </div>
  )
}
