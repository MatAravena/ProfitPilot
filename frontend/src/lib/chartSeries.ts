import type { UTCTimestamp } from 'lightweight-charts'

export interface TimeValue {
  time: UTCTimestamp
  value: number
}

/**
 * Convert backtest price points (Unix **ms**) into Lightweight-Charts area-series data:
 * seconds, sorted ascending, with duplicate timestamps collapsed (last value wins).
 *
 * Lightweight Charts' `setData` throws `Assertion failed: data must be asc ordered by time`
 * on any unsorted or duplicated timestamp. Backtest data can contain duplicate bar timestamps
 * (provider pagination overlap, a DST-boundary hourly bar) and ms→s flooring can collapse
 * near-adjacent points — so this normalisation must run before every `setData`.
 */
export function toSeriesData(prices: { timestamp: number; close: number }[]): TimeValue[] {
  const sorted = prices
    .map((p) => ({ time: Math.floor(p.timestamp / 1000) as UTCTimestamp, value: p.close }))
    .sort((a, b) => (a.time as number) - (b.time as number))

  const out: TimeValue[] = []
  for (const pt of sorted) {
    if (out.length && out[out.length - 1].time === pt.time) {
      out[out.length - 1] = pt // duplicate timestamp → keep the last point
    } else {
      out.push(pt)
    }
  }
  return out
}
