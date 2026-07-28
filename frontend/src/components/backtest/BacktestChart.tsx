import { useEffect, useRef } from 'react'
import {
  createChart, ColorType, CrosshairMode,
  type IChartApi, type ISeriesApi,
} from 'lightweight-charts'
import type { PricePoint, TradeRecord } from '@/types/backtest'
import { buildTradeMarkers } from '@/lib/tradeMarkers'
import { toSeriesData } from '@/lib/chartSeries'

interface Props {
  prices: PricePoint[]
  trades: TradeRecord[]
  height?: number
}

const THEME = { grid: '#1E293B', text: '#64748B', line: '#2563EB' }

/** Backtest price chart — Lightweight Charts area series of close prices with
 *  buy/sell trade markers. Native scroll/drag zoom (no Recharts Brush). */
export function BacktestChart({ prices, trades, height = 280 }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  // Build the chart once (recreated only if height changes).
  useEffect(() => {
    if (!hostRef.current) return
    const chart = createChart(hostRef.current, {
      width: hostRef.current.clientWidth,
      height,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: THEME.text, fontSize: 11 },
      grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
      rightPriceScale: { borderColor: THEME.grid },
      timeScale: { borderColor: THEME.grid, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    })
    const series = chart.addAreaSeries({
      lineColor: THEME.line, lineWidth: 2,
      topColor: 'rgba(37,99,235,0.20)', bottomColor: 'rgba(37,99,235,0.02)',
      priceLineVisible: false, lastValueVisible: false,
    })
    chartRef.current = chart
    seriesRef.current = series

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: hostRef.current?.clientWidth ?? 0 })
    })
    ro.observe(hostRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height])

  // Push data + markers (preserves the chart instance on updates).
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    // Lightweight Charts requires strictly-ascending, UNIQUE times; normalise (sort + dedupe)
    // before setData or it throws "data must be asc ordered by time" and unmounts the chart.
    series.setData(toSeriesData(prices))
    series.setMarkers(buildTradeMarkers(trades))
    chartRef.current?.timeScale().fitContent()
  }, [prices, trades])

  return <div ref={hostRef} className="w-full" style={{ height }} />
}
