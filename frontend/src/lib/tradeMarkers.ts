import type { SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts'
import type { TradeRecord } from '@/types/backtest'

const toSec = (ms: number): UTCTimestamp => Math.floor(ms / 1000) as UTCTimestamp

function buyMarker(time: UTCTimestamp): SeriesMarker<Time> {
  return { time, position: 'belowBar', color: '#22c55e', shape: 'arrowUp', text: 'B' }
}

function sellMarker(time: UTCTimestamp): SeriesMarker<Time> {
  return { time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'S' }
}

/** Backtest trade entries/exits → lightweight-charts markers.
 *  Long: buy at entry, sell at exit. Short: sell at entry, buy at exit. */
export function buildTradeMarkers(trades: TradeRecord[]): SeriesMarker<Time>[] {
  const markers: SeriesMarker<Time>[] = []

  for (const trade of trades) {
    const isLong = trade.side === 'long'
    const entry = toSec(trade.entry_time)
    const exit = toSec(trade.exit_time)
    markers.push(isLong ? buyMarker(entry) : sellMarker(entry))
    markers.push(isLong ? sellMarker(exit) : buyMarker(exit))
  }

  return markers.sort((a, b) => (a.time as number) - (b.time as number))
}
