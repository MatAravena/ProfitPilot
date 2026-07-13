import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ExecutionConfig } from '@/types'

// Behavioral defaults are concrete; risk fields default to null ⇒ inherit the user's risk profile.
export const DEFAULT_EXECUTION_CONFIG: ExecutionConfig = {
  size_pct: 0.02,
  allow_short: true,
  poll_seconds: null,
  stop_loss_pct: null,
  take_profit_pct: null,
  max_open_positions: null,
  max_daily_drawdown_pct: null,
  max_total_drawdown_pct: null,
  max_orders_per_minute: null,
  kill_switch_enabled: null,
}

/** fraction (0.015) → percent display string ("1.5"), trimming float noise. */
function toPct(fraction: number | null): string {
  if (fraction === null || fraction === undefined) return ''
  return String(Math.round(fraction * 1e6) / 1e4)
}

const labelCls = 'text-[10px] text-text-muted'
const inputCls =
  'w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm text-text font-mono'

/** Keeps local editable text so a field can be blanked and retyped. Only pushes a value
 * to the parent when the text parses; syncs back from the model on genuine external changes
 * (e.g. dialog opens with a different strategy) without clobbering in-progress typing. */
function useEditableNumber(
  value: number | null,
  toText: (v: number | null) => string,
  parse: (text: string) => number | null,
) {
  const [text, setText] = useState(() => toText(value))
  useEffect(() => {
    const current = parse(text)
    const same = current === null ? value === null
      : typeof value === 'number' && Math.abs(current - value) < 1e-12
    if (!same) setText(toText(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  return [text, setText] as const
}

function PctField({
  label, value, onChange, optional = false, placeholder,
}: {
  label: string
  value: number | null
  onChange: (v: number | null) => void
  optional?: boolean
  placeholder?: string
}) {
  const parse = (t: string) => (t === '' ? null : Number(t) / 100)
  const [text, setText] = useEditableNumber(value, toPct, parse)
  return (
    <div className="space-y-1">
      <label className={labelCls}>{label}</label>
      <div className="relative">
        <input
          type="text" inputMode="decimal"
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            const raw = e.target.value
            setText(raw)
            if (raw === '') { if (optional) onChange(null); return }  // required: keep last valid
            const n = Number(raw)
            if (!Number.isNaN(n)) onChange(n / 100)
          }}
          onBlur={() => setText(toPct(value))}  // always show the actual model value on blur
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
  const parse = (t: string) => (t === '' ? null : Math.trunc(Number(t)))
  const [text, setText] = useEditableNumber(value, (v) => (v ?? '').toString(), parse)
  return (
    <div className="space-y-1">
      <label className={labelCls}>{label}</label>
      <input
        type="text" inputMode="numeric"
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          const raw = e.target.value
          setText(raw)
          if (raw === '') { if (optional) onChange(null); return }  // required: keep last valid
          const n = Number(raw)
          if (!Number.isNaN(n)) onChange(Math.trunc(n))
        }}
        onBlur={() => setText((value ?? '').toString())}  // always show the actual model value on blur
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
      {/* Behavioral — always per-strategy. */}
      <div className="grid grid-cols-2 gap-2">
        <PctField label={t('strategies.config.positionSize')} value={value.size_pct}
          onChange={(v) => onChange({ size_pct: v ?? 0 })} />
        <IntField label={`${t('strategies.config.pollSeconds')} ${t('strategies.config.optional')}`}
          value={value.poll_seconds} optional
          placeholder={t('strategies.config.auto')}
          onChange={(v) => onChange({ poll_seconds: v })} />
      </div>
      <Toggle label={t('strategies.config.allowShort')} checked={value.allow_short}
        onChange={(v) => onChange({ allow_short: v })} />

      {/* Risk overrides — blank ⇒ inherit the user's risk profile (Settings). */}
      <p className="text-[10px] text-text-muted pt-1">{t('strategies.config.overridesHint')}</p>
      <div className="grid grid-cols-2 gap-2">
        <PctField label={t('strategies.config.stopLoss')} value={value.stop_loss_pct} optional
          placeholder={t('strategies.config.inherit')}
          onChange={(v) => onChange({ stop_loss_pct: v })} />
        <PctField label={t('strategies.config.takeProfit')} value={value.take_profit_pct} optional
          placeholder={t('strategies.config.inherit')}
          onChange={(v) => onChange({ take_profit_pct: v })} />
        <IntField label={t('strategies.config.maxPositions')} value={value.max_open_positions} optional
          placeholder={t('strategies.config.inherit')}
          onChange={(v) => onChange({ max_open_positions: v })} />
        <IntField label={t('strategies.config.maxOrdersMin')} value={value.max_orders_per_minute} optional
          placeholder={t('strategies.config.inherit')}
          onChange={(v) => onChange({ max_orders_per_minute: v })} />
        <PctField label={t('strategies.config.dailyDrawdown')} value={value.max_daily_drawdown_pct} optional
          placeholder={t('strategies.config.inherit')}
          onChange={(v) => onChange({ max_daily_drawdown_pct: v })} />
        <PctField label={t('strategies.config.totalDrawdown')} value={value.max_total_drawdown_pct} optional
          placeholder={t('strategies.config.inherit')}
          onChange={(v) => onChange({ max_total_drawdown_pct: v })} />
      </div>
    </div>
  )
}
