import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, RotateCcw, Grid3x3 } from 'lucide-react'
import { Select } from '@/components/ui/Select'
import { Card } from '@/components/ui/Card'
import {
  GridTuningParams,
  GridParamGroup,
  GRID_FIELD_DEFS,
  GRID_PRESETS,
  GRID_PRESET_IDS,
  DEFAULT_GRID_PARAMS,
} from '@/lib/gridParams'

const GROUPS: GridParamGroup[] = ['grid', 'regime']

interface Props {
  params: GridTuningParams
  onChange: (params: GridTuningParams) => void
  onRun: () => void
  isPending: boolean
}

/** Controlled tuning form for the grid param blocks. Presentational only — it owns no
 *  query/persistence state; the parent holds `params` and decides what "run" does.
 *  Fields are derived from GRID_FIELD_DEFS so the form can never drift from the schema. */
export function GridControls({ params, onChange, onRun, isPending }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  const setField = (group: GridParamGroup, key: string, value: number | string) => {
    onChange({ ...params, [group]: { ...params[group], [key]: value } })
  }

  // Which named preset (if any) the current params exactly match — else "custom".
  const activePreset =
    GRID_PRESET_IDS.find((id) => JSON.stringify(GRID_PRESETS[id]) === JSON.stringify(params)) ?? 'custom'

  return (
    <Card className="overflow-hidden self-stretch">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((x) => !x)}
          className="flex items-center gap-2 text-sm font-medium cursor-pointer"
        >
          <ChevronDown size={14} className={expanded ? '' : '-rotate-90 transition-transform'} />
          {t('backtests.grid.params.tune')}
        </button>
        <button
          type="button"
          onClick={onRun}
          disabled={isPending}
          className="flex items-center gap-2 bg-primary/10 border border-primary/40 text-primary rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          <Grid3x3 size={14} />
          {isPending ? t('backtests.grid.running') : t('backtests.grid.run')}
        </button>
      </div>

      {expanded && (
        <div className="p-4 flex flex-col gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 text-xs text-text-muted">
              {t('backtests.grid.params.preset')}
              <Select
                aria-label={t('backtests.grid.params.preset')}
                value={activePreset}
                onChange={(e) => {
                  const id = e.target.value
                  if (id !== 'custom' && GRID_PRESETS[id]) onChange(GRID_PRESETS[id])
                }}
                className="px-2 py-1 text-xs"
              >
                {activePreset === 'custom' && (
                  <option value="custom">{t('backtests.grid.params.presetName.custom')}</option>
                )}
                {GRID_PRESET_IDS.map((id) => (
                  <option key={id} value={id}>
                    {t(`backtests.grid.params.presetName.${id}`)}
                  </option>
                ))}
              </Select>
            </label>
            <button
              type="button"
              onClick={() => onChange(DEFAULT_GRID_PARAMS)}
              className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text border border-border rounded px-2.5 py-1 transition-colors cursor-pointer"
            >
              <RotateCcw size={12} />
              {t('backtests.grid.params.reset')}
            </button>
          </div>

          {GROUPS.map((group) => (
            <details key={group} open className="border border-border rounded-lg px-3 py-2">
              <summary className="cursor-pointer text-sm font-medium select-none">
                {t(`backtests.grid.params.group.${group}`)}
              </summary>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                {GRID_FIELD_DEFS.filter((f) => f.group === group).map((f) => {
                  const label = t(`backtests.grid.params.field.${f.key}`)
                  const value = (params[group] as unknown as Record<string, unknown>)[f.key]
                  return (
                    <label key={f.key} className="flex flex-col gap-1 text-xs text-text-muted">
                      <span>{label}</span>
                      {f.kind === 'enum' ? (
                        <Select
                          aria-label={label}
                          value={value as string}
                          onChange={(e) => setField(group, f.key, e.target.value)}
                          className="px-2 py-1"
                        >
                          {f.options.map((opt) => (
                            <option key={opt} value={opt}>
                              {t(`backtests.grid.params.spacingMode.${opt}`)}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <input
                          type="number"
                          aria-label={label}
                          value={value as number}
                          min={f.min}
                          max={f.max}
                          step={f.step}
                          onChange={(e) => {
                            const n = e.target.valueAsNumber
                            if (Number.isNaN(n)) return   // ignore a transiently-empty input
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
    </Card>
  )
}
