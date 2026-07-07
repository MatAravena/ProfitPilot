import { useTranslation } from 'react-i18next'
import type { ExecutionConfig } from '@/types'

export const DEFAULT_EXECUTION_CONFIG: ExecutionConfig = {
  size_pct: 0.02,
  stop_loss_pct: 0.015,
  take_profit_pct: null,
  max_open_positions: 5,
  max_daily_drawdown_pct: 0.03,
  max_total_drawdown_pct: 0.1,
  max_orders_per_minute: 10,
  allow_short: true,
  kill_switch_enabled: true,
  poll_seconds: null,
}

/** fraction (0.015) → percent display string ("1.5"), trimming float noise. */
function toPct(fraction: number | null): string {
  if (fraction === null || fraction === undefined) return ''
  return String(Math.round(fraction * 1e6) / 1e4)
}

const labelCls = 'text-[10px] text-text-muted'
const inputCls =
  'w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm text-text font-mono'

function PctField({
  label, value, onChange, optional = false, placeholder,
}: {
  label: string
  value: number | null
  onChange: (v: number | null) => void
  optional?: boolean
  placeholder?: string
}) {
  return (
    <div className="space-y-1">
      <label className={labelCls}>{label}</label>
      <div className="relative">
        <input
          type="number" step="0.1" min="0" inputMode="decimal"
          value={toPct(value)}
          placeholder={placeholder}
          onChange={(e) => {
            const raw = e.target.value
            if (raw === '') return onChange(optional ? null : 0)
            onChange(Number(raw) / 100)
          }}
          className={`${inputCls} pr-6`}
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-text-muted pointer-events-none">%</span>
      </div>
    </div>
  )
}

function IntField({
  label, value, onChange, optional = false, placeholder,
}: {
  label: string
  value: number | null
  onChange: (v: number | null) => void
  optional?: boolean
  placeholder?: string
}) {
  return (
    <div className="space-y-1">
      <label className={labelCls}>{label}</label>
      <input
        type="number" step="1" min={optional ? '5' : '1'} inputMode="numeric"
        value={value ?? ''}
        placeholder={placeholder}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === '') return onChange(optional ? null : 0)
          onChange(Math.trunc(Number(raw)))
        }}
        className={inputCls}
      />
    </div>
  )
}

function Toggle({
  label, checked, onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button" role="switch" aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center justify-between w-full bg-surface-2 border border-border rounded px-2.5 py-2"
    >
      <span className="text-[11px] text-text">{label}</span>
      <span className={`relative inline-block w-8 h-4 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-border'}`}>
        <span className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${checked ? 'translate-x-4' : ''}`} />
      </span>
    </button>
  )
}

interface Props {
  value: ExecutionConfig
  onChange: (patch: Partial<ExecutionConfig>) => void
}

export function ExecutionConfigForm({ value, onChange }: Props) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <PctField label={t('strategies.config.positionSize')} value={value.size_pct}
          onChange={(v) => onChange({ size_pct: v ?? 0 })} />
        <IntField label={t('strategies.config.maxPositions')} value={value.max_open_positions}
          onChange={(v) => onChange({ max_open_positions: v ?? 1 })} />
        <PctField label={t('strategies.config.stopLoss')} value={value.stop_loss_pct}
          onChange={(v) => onChange({ stop_loss_pct: v ?? 0 })} />
        <PctField label={`${t('strategies.config.takeProfit')} ${t('strategies.config.optional')}`}
          value={value.take_profit_pct} optional
          placeholder={t('strategies.config.none')}
          onChange={(v) => onChange({ take_profit_pct: v })} />
        <PctField label={t('strategies.config.dailyDrawdown')} value={value.max_daily_drawdown_pct}
          onChange={(v) => onChange({ max_daily_drawdown_pct: v ?? 0 })} />
        <PctField label={t('strategies.config.totalDrawdown')} value={value.max_total_drawdown_pct}
          onChange={(v) => onChange({ max_total_drawdown_pct: v ?? 0 })} />
        <IntField label={t('strategies.config.maxOrdersMin')} value={value.max_orders_per_minute}
          onChange={(v) => onChange({ max_orders_per_minute: v ?? 1 })} />
        <IntField label={`${t('strategies.config.pollSeconds')} ${t('strategies.config.optional')}`}
          value={value.poll_seconds} optional
          placeholder={t('strategies.config.auto')}
          onChange={(v) => onChange({ poll_seconds: v })} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Toggle label={t('strategies.config.allowShort')} checked={value.allow_short}
          onChange={(v) => onChange({ allow_short: v })} />
        <Toggle label={t('strategies.config.killSwitch')} checked={value.kill_switch_enabled}
          onChange={(v) => onChange({ kill_switch_enabled: v })} />
      </div>
    </div>
  )
}
