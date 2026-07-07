import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { TradingChart } from './TradingChart'
import { defaultIndicatorSettings, type IndicatorId, type IndicatorSettings } from '@/lib/indicatorConfig'

interface Props {
  symbol: string
  timeframe: string
  height?: number
}

// Compact preset for the dashboard widget: candles + volume + a couple of MAs,
// no oscillator panes (keeps the widget short).
function miniSettings(): IndicatorSettings {
  const s = defaultIndicatorSettings()
  const keep: IndicatorId[] = ['volume', 'sma', 'ema']
  for (const id of Object.keys(s) as IndicatorId[]) {
    s[id].enabled = keep.includes(id)
  }
  return s
}

export function PriceChart({ symbol, timeframe, height = 300 }: Props) {
  const settings = useMemo(miniSettings, [])
  const { data: candles = [], isFetching } = useQuery({
    queryKey: ['ohlcv', symbol, timeframe, 'bybit'],
    queryFn: () => api.market.ohlcv(symbol, timeframe, 500, 'bybit'),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })

  return (
    <div className="relative">
      {isFetching && (
        <div className="absolute top-3 right-3 z-10 flex items-center gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
          <span className="text-[10px] text-success font-medium">LIVE</span>
        </div>
      )}
      {candles.length ? (
        <TradingChart candles={candles} settings={settings} height={height} />
      ) : (
        <div className="flex items-center justify-center text-sm text-text-muted" style={{ height }}>
          Loading…
        </div>
      )}
    </div>
  )
}
