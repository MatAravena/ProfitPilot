import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, RotateCcw, TrendingUp } from 'lucide-react'
import {
  DcaParams,
  DcaParamGroup,
  DCA_FIELD_DEFS,
  DCA_PRESETS,
  DCA_PRESET_IDS,
  DEFAULT_DCA_PARAMS,
} from '@/lib/dcaCompareParams'

const GROUPS: DcaParamGroup[] = ['cycle', 'hunter', 'rotation']

// Only meaningful when the halving clock runs on discrete windows — hidden in gaussian mode so the
// form never shows knobs that do nothing.
const WINDOW_ONLY_KEYS = new Set([
  'sell_start_day', 'sell_end_day', 'buy_start_day', 'buy_end_day', 'ramp_days',
])

interface Props {
  params: DcaParams
  onChange: (params: DcaParams) => void
  onRun: () => void
  isPending: boolean
}

/** Controlled tuning form for the DCA-compare param blocks. Presentational only — it owns no
 *  query/persistence state; the parent holds `params` and decides what "run" does. */
export function DcaCompareControls({ params, onChange, onRun, isPending }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  const setField = (group: DcaParamGroup, key: string, value: number | string | null) => {
    onChange({ ...params, [group]: { ...params[group], [key]: value } })
  }

  // Which named preset (if any) the current params exactly match — else "custom".
  const activePreset =
    DCA_PRESET_IDS.find((id) => JSON.stringify(DCA_PRESETS[id]) === JSON.stringify(params)) ?? 'custom'

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden self-stretch">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((x) => !x)}
          className="flex items-center gap-2 text-sm font-medium cursor-pointer"
        >
          <ChevronDown size={14} className={expanded ? '' : '-rotate-90 transition-transform'} />
          {t('backtests.dca.params.tune')}
        </button>
        <button
          type="button"
          onClick={onRun}
          disabled={isPending}
          className="flex items-center gap-2 bg-primary/10 border border-primary/40 text-primary rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          <TrendingUp size={14} />
          {isPending ? t('backtests.dca.running') : t('backtests.dca.run')}
        </button>
      </div>

      {expanded && (
        <div className="p-4 flex flex-col gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 text-xs text-text-muted">
              {t('backtests.dca.params.preset')}
              <select
                aria-label={t('backtests.dca.params.preset')}
                value={activePreset}
                onChange={(e) => {
                  const id = e.target.value
                  if (id !== 'custom' && DCA_PRESETS[id]) onChange(DCA_PRESETS[id])
                }}
                className="bg-background border border-border rounded px-2 py-1 text-text text-xs cursor-pointer"
              >
                {activePreset === 'custom' && (
                  <option value="custom">{t('backtests.dca.params.presetName.custom')}</option>
                )}
                {DCA_PRESET_IDS.map((id) => (
                  <option key={id} value={id}>
                    {t(`backtests.dca.params.presetName.${id}`)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => onChange(DEFAULT_DCA_PARAMS)}
              className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text border border-border rounded px-2.5 py-1 transition-colors cursor-pointer"
            >
              <RotateCcw size={12} />
              {t('backtests.dca.params.reset')}
            </button>
          </div>

          {GROUPS.map((group) => (
            <details key={group} open className="border border-border rounded-lg px-3 py-2">
              <summary className="cursor-pointer text-sm font-medium select-none">
                {t(`backtests.dca.params.group.${group}`)}
              </summary>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                {DCA_FIELD_DEFS.filter(
                  (f) =>
                    f.group === group &&
                    (!WINDOW_ONLY_KEYS.has(f.key) || params.cycle.timing_mode === 'windows'),
                ).map((f) => {
                  const label = t(`backtests.dca.params.field.${f.key}`)
                  const value = (params[group] as Record<string, unknown>)[f.key]
                  return (
                    <label key={f.key} className="flex flex-col gap-1 text-xs text-text-muted">
                      <span>{label}</span>
                      {f.kind === 'enum' ? (
                        <select
                          aria-label={label}
                          value={value as string}
                          onChange={(e) => setField(group, f.key, e.target.value)}
                          className="bg-background border border-border rounded px-2 py-1 text-text cursor-pointer"
                        >
                          {f.options.map((opt) => (
                            <option key={opt} value={opt}>
                              {t(`backtests.dca.params.timingMode.${opt}`)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="number"
                          aria-label={label}
                          // A blank day-offset means "derive it from the gaussian params".
                          value={value === null ? '' : (value as number)}
                          placeholder={f.kind === 'day' ? t('backtests.dca.params.auto') : undefined}
                          min={f.min}
                          max={f.max}
                          step={f.step}
                          onChange={(e) => {
                            const n = e.target.valueAsNumber
                            if (Number.isNaN(n)) {
                              if (f.kind === 'day') setField(group, f.key, null)
                              return
                            }
                            setField(group, f.key, n)
                          }}
                          className="bg-background border border-border rounded px-2 py-1 text-text tabular-nums"
                        />
                      )}
                    </label>
                  )
                })}
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}
