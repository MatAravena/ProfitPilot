import type { SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts'
import type { OrderRecord, SignalRecord } from '@/types'

const toSec = (iso: string): UTCTimestamp =>
  Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp

export interface LatestSignal {
  direction: string
  time: number // unix seconds of the current bar
}

export interface MarkerInput {
  orders: OrderRecord[]
  signals: SignalRecord[]
  latestSignal?: LatestSignal | null
  showSignals?: boolean
}

/** Build lightweight-charts markers: prominent real fills, optional faint signal
 *  history, and a projected marker for the latest signal (intent, not an order). */
export function buildStrategyMarkers(
  { orders, signals, latestSignal, showSignals = false }: MarkerInput,
): SeriesMarker<Time>[] {
  const markers: SeriesMarker<Time>[] = []

  for (const o of orders) {
    if (o.filled_qty == null || o.avg_price == null || o.side == null) continue
    const isBuy = o.side === 'buy'
    markers.push({
      time: toSec(o.created_at),
      position: isBuy ? 'belowBar' : 'aboveBar',
      color: isBuy ? '#22c55e' : '#ef4444',
      shape: isBuy ? 'arrowUp' : 'arrowDown',
      text: `${o.side.toUpperCase()} ${o.filled_qty}`,
    })
  }

  if (showSignals) {
    for (const s of signals) {
      markers.push({
        time: toSec(s.generated_at),
        position: s.direction === 'short' ? 'aboveBar' : 'belowBar',
        color: 'rgba(148,163,184,0.5)',
        shape: 'circle',
        text: '',
      })
    }
  }

  if (latestSignal) {
    const isShort = latestSignal.direction === 'short'
    markers.push({
      time: latestSignal.time as UTCTimestamp,
      position: isShort ? 'aboveBar' : 'belowBar',
      color: '#3b82f6',
      shape: isShort ? 'arrowDown' : 'arrowUp',
      text: `→ ${latestSignal.direction}`,
    })
  }

  return markers.sort((a, b) => (a.time as number) - (b.time as number))
}
