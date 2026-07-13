import { AlertTriangle, FlaskConical, Radio } from 'lucide-react'

const STATUS_CONFIG: Record<string, { label: string; className: string; icon?: React.ReactNode }> = {
  draft:    { label: 'Draft',    className: 'bg-surface-2 text-text-muted' },
  paper:    { label: 'Paper',    className: 'bg-yellow-500/20 text-yellow-400', icon: <FlaskConical size={11} /> },
  live:     { label: 'Live',     className: 'bg-success/20 text-success', icon: <Radio size={11} className="animate-pulse" /> },
  paused:   { label: 'Paused',   className: 'bg-warning/20 text-warning' },
  archived: { label: 'Archived', className: 'bg-surface-2 text-text-muted' },
  halted:   { label: 'Halted',   className: 'bg-danger/20 text-danger', icon: <AlertTriangle size={11} /> },
}

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: 'bg-surface-2 text-text-muted' }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${cfg.className}`}>
      {cfg.icon}{cfg.label}
    </span>
  )
}
