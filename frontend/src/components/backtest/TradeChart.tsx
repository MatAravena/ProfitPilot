import {
  ComposedChart, Area, Scatter, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import type { TradeRecord, PricePoint } from '@/types/backtest'
import { formatCurrency } from '@/lib/utils'

interface Props {
  prices: PricePoint[]
  trades: TradeRecord[]
  timeframe: string
  height?: number
}

interface ChartPoint {
  time: number   // Unix seconds
  close: number
  buy?: number   // price at buy entry
  sell?: number  // price at sell exit
}

function fmtTime(ts: number, timeframe: string): string {
  const d = new Date(ts * 1000)
  if (['1m', '5m', '15m', '1h', '4h'].includes(timeframe)) {
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { year: '2-digit', month: 'short', day: 'numeric' })
}

// Custom triangle dots for buy/sell scatter points
function BuyDot(props: { cx?: number; cy?: number }) {
  const { cx = 0, cy = 0 } = props
  return (
    <polygon
      points={`${cx},${cy - 7} ${cx - 5},${cy + 3} ${cx + 5},${cy + 3}`}
      fill="#22c55e"
      stroke="#16161f"
      strokeWidth={1}
    />
  )
}

function SellDot(props: { cx?: number; cy?: number }) {
  const { cx = 0, cy = 0 } = props
  return (
    <polygon
      points={`${cx},${cy + 7} ${cx - 5},${cy - 3} ${cx + 5},${cy - 3}`}
      fill="#ef4444"
      stroke="#16161f"
      strokeWidth={1}
    />
  )
}

export function TradeChart({ prices, trades, timeframe, height = 300 }: Props) {
  if (!prices.length) return null

  // Convert ms timestamps to seconds, mark trade entries and exits
  const byTime = new Map<number, ChartPoint>()

  for (const p of prices) {
    const t = Math.floor(p.timestamp / 1000)
    byTime.set(t, { time: t, close: p.close })
  }

  for (const trade of trades) {
    const entryT = Math.floor(trade.entry_time / 1000)
    const exitT = Math.floor(trade.exit_time / 1000)

    // Find the closest price point for entry
    const entryPt = byTime.get(entryT) ?? findClosest(byTime, entryT)
    if (entryPt) {
      trade.side === 'long'
        ? (entryPt.buy = trade.entry_price)
        : (entryPt.sell = trade.entry_price)  // short entry = sell
    }

    // Exit
    const exitPt = byTime.get(exitT) ?? findClosest(byTime, exitT)
    if (exitPt) {
      trade.side === 'long'
        ? (exitPt.sell = trade.exit_price)    // long exit = sell
        : (exitPt.buy = trade.exit_price)     // short exit = buy
    }
  }

  const data = Array.from(byTime.values()).sort((a, b) => a.time - b.time)
  const buyPoints = data.filter((d) => d.buy !== undefined).map((d) => ({ time: d.time, price: d.buy! }))
  const sellPoints = data.filter((d) => d.sell !== undefined).map((d) => ({ time: d.time, price: d.sell! }))

  const allPrices = data.map((d) => d.close)
  const minPrice = Math.min(...allPrices) * 0.998
  const maxPrice = Math.max(...allPrices) * 1.002

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
        <XAxis
          dataKey="time"
          type="number"
          domain={['dataMin', 'dataMax']}
          scale="time"
          tickFormatter={(ts) => fmtTime(ts as number, timeframe)}
          tick={{ fill: '#64748B', fontSize: 10 }}
          axisLine={{ stroke: '#1E293B' }}
          tickLine={false}
          minTickGap={80}
          allowDuplicatedCategory={false}
        />
        <YAxis
          tickFormatter={(v) => formatCurrency(v as number)}
          tick={{ fill: '#64748B', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={72}
          domain={[minPrice, maxPrice]}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#16161f',
            border: '1px solid #1E293B',
            borderRadius: '8px',
            color: '#f1f5f9',
            fontSize: 12,
          }}
          labelFormatter={(ts) => fmtTime(ts as number, timeframe)}
          formatter={(value, name) => [
            formatCurrency(Number(value)),
            name === 'close' ? 'Price' : name === 'price' ? undefined : name,
          ]}
        />
        <Legend
          wrapperStyle={{ fontSize: 11, color: '#64748B' }}
          formatter={(value) => (value === 'buy' ? '▲ Buy' : value === 'sell' ? '▼ Sell' : 'Price')}
        />

        {/* Price line */}
        <Area
          data={data}
          type="monotone"
          dataKey="close"
          stroke="#2563EB"
          strokeWidth={1.5}
          fill="#2563EB"
          fillOpacity={0.07}
          dot={false}
          activeDot={false}
          isAnimationActive={false}
          legendType="line"
        />

        {/* Buy markers */}
        <Scatter
          data={buyPoints}
          dataKey="price"
          name="buy"
          fill="#22c55e"
          shape={<BuyDot />}
          isAnimationActive={false}
        />

        {/* Sell markers */}
        <Scatter
          data={sellPoints}
          dataKey="price"
          name="sell"
          fill="#ef4444"
          shape={<SellDot />}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function findClosest(map: Map<number, ChartPoint>, target: number): ChartPoint | undefined {
  let best: ChartPoint | undefined
  let bestDist = Infinity
  for (const [t, pt] of map) {
    const d = Math.abs(t - target)
    if (d < bestDist) { bestDist = d; best = pt }
  }
  return best
}
