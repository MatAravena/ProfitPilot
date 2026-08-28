interface SwitchProps {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  /** Compact form: knob + label inline, no bordered row. For toolbar-style placements. */
  bare?: boolean
}

/** Accessible on/off switch (role="switch") styled to match the app's dark theme —
 *  use in place of a raw <input type="checkbox"> wherever the app needs a boolean toggle. */
export function Switch({ label, checked, onChange, bare = false }: SwitchProps) {
  const knob = (
    <span className={`relative inline-block w-8 h-4 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-border'}`}>
      <span className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${checked ? 'translate-x-4' : ''}`} />
    </span>
  )

  if (bare) {
    return (
      <button
        type="button" role="switch" aria-checked={checked}
        onClick={() => onChange(!checked)}
        className="flex items-center gap-1.5 text-[11px] text-text-muted"
      >
        {knob}
        {label}
      </button>
    )
  }

  return (
    <button
      type="button" role="switch" aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center justify-between w-full bg-surface-2 border border-border rounded px-2.5 py-2"
    >
      <span className="text-[11px] text-text">{label}</span>
      {knob}
    </button>
  )
}
