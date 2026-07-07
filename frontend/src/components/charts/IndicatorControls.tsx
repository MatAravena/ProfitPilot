import { INDICATORS, type IndicatorId, type IndicatorSettings } from '@/lib/indicatorConfig'
import { cn } from '@/lib/utils'

interface Props {
  settings: IndicatorSettings
  onChange: (next: IndicatorSettings) => void
}

export function IndicatorControls({ settings, onChange }: Props) {
  function toggle(id: IndicatorId) {
    onChange({ ...settings, [id]: { ...settings[id], enabled: !settings[id].enabled } })
  }

  function setParam(id: IndicatorId, key: string, value: number) {
    onChange({
      ...settings,
      [id]: { ...settings[id], params: { ...settings[id].params, [key]: value } },
    })
  }

  const overlays = INDICATORS.filter((d) => d.kind === 'overlay')
  const panes = INDICATORS.filter((d) => d.kind === 'pane')

  const renderGroup = (title: string, defs: typeof INDICATORS) => (
    <div className="space-y-2">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{title}</h4>
      <div className="space-y-1.5">
        {defs.map((def) => {
          const state = settings[def.id]
          return (
            <div key={def.id} className="rounded-lg border border-border bg-surface-2/40 px-2.5 py-2">
              <button
                onClick={() => toggle(def.id)}
                className="flex w-full items-center gap-2 cursor-pointer"
              >
                <span
                  className={cn(
                    'flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border',
                    state.enabled ? 'border-transparent' : 'border-border',
                  )}
                  style={state.enabled ? { backgroundColor: def.color } : undefined}
                >
                  {state.enabled && (
                    <svg viewBox="0 0 10 10" className="h-2.5 w-2.5 text-black">
                      <path d="M2 5l2 2 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: def.color }} />
                <span className={cn('text-xs font-medium', state.enabled ? 'text-text' : 'text-text-muted')}>
                  {def.label}
                </span>
              </button>

              {state.enabled && def.params.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2 pl-5">
                  {def.params.map((pd) => (
                    <label key={pd.key} className="flex items-center gap-1">
                      <span className="text-[10px] text-text-muted">{pd.label}</span>
                      <input
                        type="number"
                        value={state.params[pd.key]}
                        min={pd.min}
                        max={pd.max}
                        step={pd.step}
                        onChange={(e) => {
                          const v = Number(e.target.value)
                          if (!Number.isNaN(v)) setParam(def.id, pd.key, v)
                        }}
                        className="w-14 rounded border border-border bg-surface px-1.5 py-0.5 text-[11px] text-text focus:border-primary focus:outline-none"
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="space-y-4">
      {renderGroup('Overlays', overlays)}
      {renderGroup('Oscillators', panes)}
    </div>
  )
}
