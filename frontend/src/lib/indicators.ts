// Pure technical-indicator math for the trading chart.
// All functions operate on ascending-by-time OHLCV candles and return points
// aligned to candle time (Unix seconds). Indicators emit points only where they
// are mathematically defined (warm-up periods are skipped), which is exactly what
// lightweight-charts' setData() expects.

import type { OHLCVCandle } from '@/types'

export interface LinePoint {
  time: number
  value: number
}

export interface HistPoint {
  time: number
  value: number
  color?: string
}

// ── helpers ────────────────────────────────────────────────────────────────

/** EMA over a raw value series. Returns same-length array; undefined during warm-up. */
function emaSeries(values: number[], period: number): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length).fill(undefined)
  if (period <= 0 || values.length < period) return out
  const k = 2 / (period + 1)
  // Seed with SMA of the first `period` values.
  let prev = 0
  for (let i = 0; i < period; i++) prev += values[i]
  prev /= period
  out[period - 1] = prev
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

const closes = (c: OHLCVCandle[]) => c.map((b) => b.close)

// ── overlays (price scale) ───────────────────────────────────────────────────

export function sma(candles: OHLCVCandle[], period: number): LinePoint[] {
  const out: LinePoint[] = []
  if (period <= 0) return out
  let sum = 0
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close
    if (i >= period) sum -= candles[i - period].close
    if (i >= period - 1) out.push({ time: candles[i].time, value: sum / period })
  }
  return out
}

export function ema(candles: OHLCVCandle[], period: number): LinePoint[] {
  const series = emaSeries(closes(candles), period)
  const out: LinePoint[] = []
  for (let i = 0; i < candles.length; i++) {
    const v = series[i]
    if (v !== undefined) out.push({ time: candles[i].time, value: v })
  }
  return out
}

export function wma(candles: OHLCVCandle[], period: number): LinePoint[] {
  const out: LinePoint[] = []
  if (period <= 0 || candles.length < period) return out
  const denom = (period * (period + 1)) / 2
  for (let i = period - 1; i < candles.length; i++) {
    let weighted = 0
    for (let j = 0; j < period; j++) {
      weighted += candles[i - period + 1 + j].close * (j + 1)
    }
    out.push({ time: candles[i].time, value: weighted / denom })
  }
  return out
}

export interface BollingerBands {
  upper: LinePoint[]
  middle: LinePoint[]
  lower: LinePoint[]
}

export function bollinger(candles: OHLCVCandle[], period: number, stdDevMult: number): BollingerBands {
  const bands: BollingerBands = { upper: [], middle: [], lower: [] }
  if (period <= 0 || candles.length < period) return bands
  for (let i = period - 1; i < candles.length; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += candles[j].close
    const mean = sum / period
    let variance = 0
    for (let j = i - period + 1; j <= i; j++) {
      const d = candles[j].close - mean
      variance += d * d
    }
    const sd = Math.sqrt(variance / period)
    const t = candles[i].time
    bands.middle.push({ time: t, value: mean })
    bands.upper.push({ time: t, value: mean + stdDevMult * sd })
    bands.lower.push({ time: t, value: mean - stdDevMult * sd })
  }
  return bands
}

/** Cumulative VWAP anchored to the first candle of the loaded range. */
export function vwap(candles: OHLCVCandle[]): LinePoint[] {
  const out: LinePoint[] = []
  let cumPV = 0
  let cumVol = 0
  for (const c of candles) {
    const typical = (c.high + c.low + c.close) / 3
    cumPV += typical * c.volume
    cumVol += c.volume
    if (cumVol > 0) out.push({ time: c.time, value: cumPV / cumVol })
  }
  return out
}

/** Parabolic SAR (Wilder). step = acceleration factor increment, max = AF cap. */
export function parabolicSAR(candles: OHLCVCandle[], step = 0.02, max = 0.2): LinePoint[] {
  const out: LinePoint[] = []
  if (candles.length < 2) return out

  let uptrend = candles[1].close >= candles[0].close
  let af = step
  let ep = uptrend ? candles[0].high : candles[0].low
  let sar = uptrend ? candles[0].low : candles[0].high

  for (let i = 1; i < candles.length; i++) {
    const c = candles[i]
    sar = sar + af * (ep - sar)

    if (uptrend) {
      // SAR cannot exceed the prior two lows.
      sar = Math.min(sar, candles[i - 1].low, candles[i >= 2 ? i - 2 : i - 1].low)
      if (c.high > ep) { ep = c.high; af = Math.min(af + step, max) }
      if (c.low < sar) { // flip to downtrend
        uptrend = false; sar = ep; ep = c.low; af = step
      }
    } else {
      sar = Math.max(sar, candles[i - 1].high, candles[i >= 2 ? i - 2 : i - 1].high)
      if (c.low < ep) { ep = c.low; af = Math.min(af + step, max) }
      if (c.high > sar) { // flip to uptrend
        uptrend = true; sar = ep; ep = c.high; af = step
      }
    }
    out.push({ time: c.time, value: sar })
  }
  return out
}

// ── oscillators (separate panes) ─────────────────────────────────────────────

export function rsi(candles: OHLCVCandle[], period: number): LinePoint[] {
  const out: LinePoint[] = []
  if (period <= 0 || candles.length <= period) return out
  let avgGain = 0
  let avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const diff = candles[i].close - candles[i - 1].close
    if (diff >= 0) avgGain += diff
    else avgLoss -= diff
  }
  avgGain /= period
  avgLoss /= period
  const rsiVal = (g: number, l: number) => (l === 0 ? 100 : 100 - 100 / (1 + g / l))
  out.push({ time: candles[period].time, value: rsiVal(avgGain, avgLoss) })
  for (let i = period + 1; i < candles.length; i++) {
    const diff = candles[i].close - candles[i - 1].close
    const gain = diff > 0 ? diff : 0
    const loss = diff < 0 ? -diff : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    out.push({ time: candles[i].time, value: rsiVal(avgGain, avgLoss) })
  }
  return out
}

export interface MACDResult {
  macd: LinePoint[]
  signal: LinePoint[]
  histogram: HistPoint[]
}

export function macd(
  candles: OHLCVCandle[],
  fast: number,
  slow: number,
  signalPeriod: number,
): MACDResult {
  const result: MACDResult = { macd: [], signal: [], histogram: [] }
  const c = closes(candles)
  const fastE = emaSeries(c, fast)
  const slowE = emaSeries(c, slow)

  // MACD line where both EMAs exist.
  const macdRaw: (number | undefined)[] = new Array(candles.length).fill(undefined)
  const macdValues: number[] = []
  const macdIdx: number[] = []
  for (let i = 0; i < candles.length; i++) {
    if (fastE[i] !== undefined && slowE[i] !== undefined) {
      const v = (fastE[i] as number) - (slowE[i] as number)
      macdRaw[i] = v
      macdValues.push(v)
      macdIdx.push(i)
      result.macd.push({ time: candles[i].time, value: v })
    }
  }

  // Signal = EMA of the compacted MACD series, mapped back to candle indices.
  const signalE = emaSeries(macdValues, signalPeriod)
  for (let j = 0; j < macdIdx.length; j++) {
    const sv = signalE[j]
    if (sv === undefined) continue
    const i = macdIdx[j]
    result.signal.push({ time: candles[i].time, value: sv })
    const hist = (macdRaw[i] as number) - sv
    result.histogram.push({
      time: candles[i].time,
      value: hist,
      color: hist >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)',
    })
  }
  return result
}

export interface StochasticResult {
  k: LinePoint[]
  d: LinePoint[]
}

export function stochastic(
  candles: OHLCVCandle[],
  kPeriod: number,
  dPeriod: number,
  smooth: number,
): StochasticResult {
  const result: StochasticResult = { k: [], d: [] }
  if (kPeriod <= 0 || candles.length < kPeriod) return result

  // Raw %K
  const rawK: { time: number; value: number }[] = []
  for (let i = kPeriod - 1; i < candles.length; i++) {
    let hh = -Infinity
    let ll = Infinity
    for (let j = i - kPeriod + 1; j <= i; j++) {
      if (candles[j].high > hh) hh = candles[j].high
      if (candles[j].low < ll) ll = candles[j].low
    }
    const denom = hh - ll
    rawK.push({ time: candles[i].time, value: denom === 0 ? 0 : ((candles[i].close - ll) / denom) * 100 })
  }

  // Smoothed %K (SMA of raw %K over `smooth`)
  const smoothK: { time: number; value: number }[] = []
  for (let i = smooth - 1; i < rawK.length; i++) {
    let sum = 0
    for (let j = i - smooth + 1; j <= i; j++) sum += rawK[j].value
    smoothK.push({ time: rawK[i].time, value: sum / smooth })
  }
  result.k = smoothK

  // %D = SMA of %K over `dPeriod`
  for (let i = dPeriod - 1; i < smoothK.length; i++) {
    let sum = 0
    for (let j = i - dPeriod + 1; j <= i; j++) sum += smoothK[j].value
    result.d.push({ time: smoothK[i].time, value: sum / dPeriod })
  }
  return result
}

/** Average True Range (Wilder smoothing). */
export function atr(candles: OHLCVCandle[], period: number): LinePoint[] {
  const out: LinePoint[] = []
  if (period <= 0 || candles.length <= period) return out
  const tr: number[] = []
  for (let i = 1; i < candles.length; i++) {
    const c = candles[i]
    const prevClose = candles[i - 1].close
    tr.push(Math.max(c.high - c.low, Math.abs(c.high - prevClose), Math.abs(c.low - prevClose)))
  }
  // tr[i] corresponds to candles[i+1].
  let prev = 0
  for (let i = 0; i < period; i++) prev += tr[i]
  prev /= period
  out.push({ time: candles[period].time, value: prev })
  for (let i = period; i < tr.length; i++) {
    prev = (prev * (period - 1) + tr[i]) / period
    out.push({ time: candles[i + 1].time, value: prev })
  }
  return out
}
