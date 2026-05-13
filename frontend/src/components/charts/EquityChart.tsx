import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { formatCurrency } from '@/lib/utils'

interface Props {
  data: { time: number; value: number }[]
  height?: number
}

export function EquityChart({ data, height = 240 }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
        <XAxis
          dataKey="time"
          tickFormatter={(ts) =>
            new Date((ts as number) * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })
          }
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
          formatter={(value) => [formatCurrency(Number(value)), 'Equity']}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#2563EB"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: '#2563EB', stroke: '#16161f', strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
