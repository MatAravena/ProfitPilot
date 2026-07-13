import { useEffect, useMemo, useRef } from 'react'
import {
  createChart, ColorType, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type UTCTimestamp, type Time, type SeriesMarker,
} from 'lightweight-charts'
import type { OHLCVCandle } from '@/types'
import {
  INDICATOR_MAP, type IndicatorId, type IndicatorSettings,
} from '@/lib/indicatorConfig'
import {
  sma, ema, wma, bollinger, vwap, parabolicSAR, rsi, macd, stochastic, atr,
  type LinePoint,
} from '@/lib/indicators'

export interface CrosshairSnapshot {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  /** indicator label → value at this time (e.g. "RSI" → 61.2) */
  indicators: Record<string, number>
}

interface Props {
  candles: OHLCVCandle[]
  settings: IndicatorSettings
  /** Fired on crosshair hover; null when the pointer leaves the chart. */
  onHover?: (snap: CrosshairSnapshot | null) => void
  height?: number
  /** Trade / signal markers to draw on the candle series. */
  markers?: SeriesMarker<Time>[]
}

const PANE_HEIGHT = 120
const THEME = {
  grid: '#1E293B',
  text: '#64748B',
  up: '#22c55e',
  down: '#ef4444',
}

const t = (sec: number) => sec as UTCTimestamp

const baseChartOptions = (showTime: boolean) => ({
  layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: THEME.text, fontSize: 11 },
  grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
  rightPriceScale: { borderColor: THEME.grid },
  timeScale: { borderColor: THEME.grid, timeVisible: true, secondsVisible: false, visible: showTime },
  crosshair: { mode: CrosshairMode.Normal },
  handleScale: true,
  handleScroll: true,
})

// ── per-indicator computation → flat line/hist series for lookup & drawing ────

interface ComputedSeries {
  overlays: { key: string; label: string; color: string; data: LinePoint[]; dashed?: boolean }[]
  volume: { time: number; value: number; color: string }[] | null
  panes: {
    id: IndicatorId
    series: { key: string; type: 'line' | 'hist'; color: string; data: LinePoint[] }[]
    refLines: number[]
  }[]
  /** label → (time → value) for crosshair readouts */
  lookup: Map<string, Map<number, number>>
}

function buildLookup(map: Map<string, Map<number, number>>, label: string, data: LinePoint[]) {
  const m = new Map<number, number>()
  for (const pt of data) m.set(pt.time, pt.value)
  map.set(label, m)
}

function computeSeries(candles: OHLCVCandle[], settings: IndicatorSettings): ComputedSeries {
  const result: ComputedSeries = { overlays: [], volume: null, panes: [], lookup: new Map() }
  const on = (id: IndicatorId) => settings[id]?.enabled
  const prm = (id: IndicatorId, k: string) => settings[id].params[k]
  const color = (id: IndicatorId) => INDICATOR_MAP[id].color

  if (on('sma')) {
    const d = sma(candles, prm('sma', 'period'))
    result.overlays.push({ key: 'sma', label: `SMA ${prm('sma', 'period')}`, color: color('sma'), data: d })
    buildLookup(result.lookup, 'SMA', d)
  }
  if (on('ema')) {
    const d = ema(candles, prm('ema', 'period'))
    result.overlays.push({ key: 'ema', label: `EMA ${prm('ema', 'period')}`, color: color('ema'), data: d })
    buildLookup(result.lookup, 'EMA', d)
  }
  if (on('wma')) {
    const d = wma(candles, prm('wma', 'period'))
    result.overlays.push({ key: 'wma', label: `WMA ${prm('wma', 'period')}`, color: color('wma'), data: d })
    buildLookup(result.lookup, 'WMA', d)
  }
  if (on('bollinger')) {
    const b = bollinger(candles, prm('bollinger', 'period'), prm('bollinger', 'stdDev'))
    result.overlays.push({ key: 'bb.u', label: 'BB Upper', color: color('bollinger'), data: b.upper })
    result.overlays.push({ key: 'bb.m', label: 'BB Mid', color: color('bollinger'), data: b.middle, dashed: true })
    result.overlays.push({ key: 'bb.l', label: 'BB Lower', color: color('bollinger'), data: b.lower })
    buildLookup(result.lookup, 'BB Mid', b.middle)
  }
  if (on('vwap')) {
    const d = vwap(candles)
    result.overlays.push({ key: 'vwap', label: 'VWAP', color: color('vwap'), data: d })
    buildLookup(result.lookup, 'VWAP', d)
  }
  if (on('psar')) {
    const d = parabolicSAR(candles, prm('psar', 'step'), prm('psar', 'max'))
    result.overlays.push({ key: 'psar', label: 'PSAR', color: color('psar'), data: d, dashed: true })
    buildLookup(result.lookup, 'PSAR', d)
  }

  if (on('volume')) {
    result.volume = candles.map((c) => ({
      time: c.time,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(34,197,94,0.45)' : 'rgba(239,68,68,0.45)',
    }))
  }

  if (on('rsi')) {
    const d = rsi(candles, prm('rsi', 'period'))
    result.panes.push({ id: 'rsi', refLines: [70, 30], series: [{ key: 'rsi', type: 'line', color: color('rsi'), data: d }] })
    buildLookup(result.lookup, 'RSI', d)
  }
  if (on('macd')) {
    const m = macd(candles, prm('macd', 'fast'), prm('macd', 'slow'), prm('macd', 'signal'))
    result.panes.push({
      id: 'macd', refLines: [0],
      series: [
        { key: 'macd.hist', type: 'hist', color: color('macd'), data: m.histogram },
        { key: 'macd.macd', type: 'line', color: '#2563eb', data: m.macd },
        { key: 'macd.signal', type: 'line', color: '#f59e0b', data: m.signal },
      ],
    })
    buildLookup(result.lookup, 'MACD', m.macd)
  }
  if (on('stochastic')) {
    const s = stochastic(candles, prm('stochastic', 'k'), prm('stochastic', 'd'), prm('stochastic', 'smooth'))
    result.panes.push({
      id: 'stochastic', refLines: [80, 20],
      series: [
        { key: 'stoch.k', type: 'line', color: color('stochastic'), data: s.k },
        { key: 'stoch.d', type: 'line', color: '#a3e635', data: s.d },
      ],
    })
    buildLookup(result.lookup, '%K', s.k)
  }
  if (on('atr')) {
    const d = atr(candles, prm('atr', 'period'))
    result.panes.push({ id: 'atr', refLines: [], series: [{ key: 'atr', type: 'line', color: color('atr'), data: d }] })
    buildLookup(result.lookup, 'ATR', d)
  }

  return result
}

export function TradingChart({ candles, settings, onHover, height = 420, markers }: Props) {
  const priceRef = useRef<HTMLDivElement>(null)
  const paneHostRef = useRef<HTMLDivElement>(null)
  const chartsRef = useRef<IChartApi[]>([])
  const seriesRef = useRef<Map<string, ISeriesApi<'Line' | 'Histogram' | 'Candlestick'>>>(new Map())
  const computed = useMemo(() => computeSeries(candles, settings), [candles, settings])

  // Structural signature: rebuild charts only when the set of enabled indicators
  // (and thus the pane layout / series objects) changes — NOT on param/data edits.
  const structuralKey = useMemo(() => {
    const overlays = computed.overlays.map((o) => o.key).join(',')
    const panes = computed.panes.map((p) => p.id).join(',')
    return `${overlays}|${panes}|vol:${computed.volume ? 1 : 0}|h:${height}`
  }, [computed, height])

  // ── build charts + series skeleton ──
  useEffect(() => {
    if (!priceRef.current || !paneHostRef.current) return
    const charts: IChartApi[] = []
    const series = new Map<string, ISeriesApi<'Line' | 'Histogram' | 'Candlestick'>>()
    const paneIds = computed.panes.map((p) => p.id)
    const lastIsPane = paneIds.length > 0

    // Main price chart
    const main = createChart(priceRef.current, {
      ...baseChartOptions(!lastIsPane),
      width: priceRef.current.clientWidth,
      height: height - paneIds.length * PANE_HEIGHT,
    })
    const candle = main.addCandlestickSeries({
      upColor: THEME.up, downColor: THEME.down, borderVisible: false,
      wickUpColor: THEME.up, wickDownColor: THEME.down,
    })
    series.set('__candle', candle)
    charts.push(main)

    for (const o of computed.overlays) {
      const s = main.addLineSeries({
        color: o.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid, crosshairMarkerVisible: false,
      })
      series.set(o.key, s)
    }
    if (computed.volume) {
      const vol = main.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'volume', lastValueVisible: false })
      main.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      series.set('__volume', vol)
    }

    // Oscillator panes (one chart each), stacked below
    computed.panes.forEach((pane, idx) => {
      const host = document.createElement('div')
      host.style.width = '100%'
      host.style.height = `${PANE_HEIGHT}px`
      host.style.position = 'relative'
      const labelEl = document.createElement('span')
      labelEl.textContent = INDICATOR_MAP[pane.id].label
      labelEl.style.cssText = 'position:absolute;left:6px;top:2px;z-index:2;font-size:10px;color:#64748B;font-weight:600;pointer-events:none'
      host.appendChild(labelEl)
      paneHostRef.current!.appendChild(host)

      const isLast = idx === computed.panes.length - 1
      const pc = createChart(host, {
        ...baseChartOptions(isLast),
        width: host.clientWidth, height: PANE_HEIGHT,
      })
      pane.series.forEach((sd) => {
        const s = sd.type === 'hist'
          ? pc.addHistogramSeries({ color: sd.color, priceLineVisible: false, lastValueVisible: false })
          : pc.addLineSeries({ color: sd.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: true })
        series.set(sd.key, s)
      })
      // Reference lines (70/30, 80/20, 0…)
      if (pane.series[0]) {
        for (const lvl of pane.refLines) {
          pane.series[0].type !== 'hist' && series.get(pane.series[0].key)?.createPriceLine({
            price: lvl, color: THEME.grid, lineWidth: 1, lineStyle: LineStyle.Dashed,
            axisLabelVisible: true, title: '',
          })
        }
      }
      charts.push(pc)
    })

    // Sync visible time range across every chart.
    let syncing = false
    const syncFns = charts.map((c) => () => {
      if (syncing) return
      const range = c.timeScale().getVisibleLogicalRange()
      if (!range) return
      syncing = true
      for (const other of charts) if (other !== c) other.timeScale().setVisibleLogicalRange(range)
      syncing = false
    })
    charts.forEach((c, i) => c.timeScale().subscribeVisibleLogicalRangeChange(syncFns[i]))

    // Crosshair → metrics snapshot (driven by the main chart).
    const onMove = (param: { time?: Time; point?: { x: number; y: number } }) => {
      if (!onHover) return
      if (param.time === undefined || !param.point) { onHover(null); return }
      const time = param.time as number
      const c = candles.find((b) => b.time === time)
      if (!c) { onHover(null); return }
      const indicators: Record<string, number> = {}
      for (const [label, m] of computed.lookup) {
        const v = m.get(time)
        if (v !== undefined) indicators[label] = v
      }
      onHover({ time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume, indicators })
    }
    main.subscribeCrosshairMove(onMove)

    // Responsive width
    const ro = new ResizeObserver(() => {
      const w = priceRef.current?.clientWidth ?? 0
      for (const c of charts) c.applyOptions({ width: w })
    })
    if (priceRef.current) ro.observe(priceRef.current)

    chartsRef.current = charts
    seriesRef.current = series

    return () => {
      ro.disconnect()
      main.unsubscribeCrosshairMove(onMove)
      for (const c of charts) c.remove()
      chartsRef.current = []
      seriesRef.current = new Map()
      if (paneHostRef.current) paneHostRef.current.innerHTML = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structuralKey])

  // ── push data into existing series (preserves zoom on live/param updates) ──
  useEffect(() => {
    const series = seriesRef.current
    if (!series.size) return
    const candle = series.get('__candle')
    candle?.setData(candles.map((c) => ({
      time: t(c.time), open: c.open, high: c.high, low: c.low, close: c.close,
    })) as never)
    candle?.setMarkers(markers ?? [])

    for (const o of computed.overlays) {
      series.get(o.key)?.setData(o.data.map((p) => ({ time: t(p.time), value: p.value })) as never)
    }
    if (computed.volume) {
      series.get('__volume')?.setData(computed.volume.map((v) => ({ time: t(v.time), value: v.value, color: v.color })) as never)
    }
    for (const pane of computed.panes) {
      for (const sd of pane.series) {
        series.get(sd.key)?.setData(sd.data.map((p) => ({ time: t(p.time), value: p.value })) as never)
      }
    }
  }, [computed, candles, markers])

  return (
    <div className="w-full" style={{ height }}>
      <div ref={priceRef} className="w-full" style={{ height: height - computed.panes.length * PANE_HEIGHT }} />
      <div ref={paneHostRef} className="w-full" />
    </div>
  )
}
