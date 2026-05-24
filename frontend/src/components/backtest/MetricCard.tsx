import { cn } from '@/lib/utils'

interface Props {
  label: string
  value: string
  positive: boolean
  icon: React.ElementType
}

export function MetricCard({ label, value, positive, icon: Icon }: Props) {
  return (
    <div className="bg-surface border border-border rounded-xl p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] text-text-muted font-medium">{label}</span>
        <Icon size={12} className="text-text-muted" strokeWidth={1.5} />
      </div>
      <p className={cn('text-base font-bold', positive ? 'text-success' : 'text-danger')}>{value}</p>
    </div>
  )
}
