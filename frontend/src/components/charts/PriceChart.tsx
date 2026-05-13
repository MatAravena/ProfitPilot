import { useQuery } from '@tanstack/react-query'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { api } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'

interface Props {
  symbol: string
  timeframe: string
  height?: number
}

function fmtAxisTime(ts: number, timeframe: string): string {
  const d = new Date(ts * 1000)
  if (['1m', '5m', '15m', '1h', '4h'].includes(timeframe)) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function PriceChart({ symbol, timeframe, height = 280 }: Props) {
  const { data: ohlcv = [], isFetching } = useQuery({
    queryKey: ['ohlcv', symbol, timeframe, 'bybit'],
    queryFn: () => api.market.ohlcv(symbol, timeframe, 500, 'bybit'),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })

  const chartData = ohlcv.map((c) => ({ time: c.time, value: c.close }))

  return (
    <div className="relative">
      {isFetching && (
        <div className="absolute top-3 right-3 z-10 flex items-center gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
          <span className="text-[10px] text-success font-medium">LIVE</span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2563EB" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#2563EB" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
          <XAxis
            dataKey="time"
            tickFormatter={(ts) => fmtAxisTime(ts as number, timeframe)}
            tick={{ fill: '#64748B', fontSize: 10 }}
            axisLine={{ stroke: '#1E293B' }}
            tickLine={false}
            minTickGap={60}
          />
          <YAxis
            tickFormatter={(v) => formatCurrency(v as number)}
            tick={{ fill: '#64748B', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={72}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#16161f',
              border: '1px solid #1E293B',
              borderRadius: '8px',
              color: '#f1f5f9',
              fontSize: 12,
            }}
            labelFormatter={(ts) => new Date((ts as number) * 1000).toLocaleString()}
            formatter={(value) => [formatCurrency(Number(value)), 'Close']}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#2563EB"
            strokeWidth={2}
            fill="url(#priceGradient)"
            dot={false}
            activeDot={{ r: 4, fill: '#2563EB', stroke: '#16161f', strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
