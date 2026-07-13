import { useState } from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { ExecutionConfigForm, DEFAULT_EXECUTION_CONFIG } from './ExecutionConfigForm'
import type { ExecutionConfig } from '@/types'

function Harness() {
  const [cfg, setCfg] = useState<ExecutionConfig>(DEFAULT_EXECUTION_CONFIG)
  return <ExecutionConfigForm value={cfg} onChange={(p) => setCfg((prev) => ({ ...prev, ...p }))} />
}

describe('ExecutionConfigForm', () => {
  it('lets a required field be cleared and retyped without snapping to 0', () => {
    render(<Harness />)
    // size_pct 0.02 → "2" in the Position size field (unique display value).
    const size = screen.getByDisplayValue('2') as HTMLInputElement

    fireEvent.change(size, { target: { value: '' } })
    expect(size.value).toBe('')          // blanked, not coerced to "0"

    fireEvent.change(size, { target: { value: '3' } })
    expect(size.value).toBe('3')
  })

  it('resyncs a blanked required field to the model value on blur', () => {
    render(<Harness />)
    const size = screen.getByDisplayValue('2') as HTMLInputElement
    fireEvent.change(size, { target: { value: '' } })
    expect(size.value).toBe('')
    fireEvent.blur(size)
    expect(size.value).toBe('2')      // restored from the model (0.02) — no silent divergence
  })

  it('risk override fields start blank (inherit) and stay cleared', () => {
    render(<Harness />)
    // All risk overrides default to null → blank inputs with the "Inherit" placeholder.
    const overrides = screen.getAllByPlaceholderText('Inherit') as HTMLInputElement[]
    expect(overrides.length).toBeGreaterThan(0)
    const sl = overrides[0]
    expect(sl.value).toBe('')
    fireEvent.change(sl, { target: { value: '2' } })
    expect(sl.value).toBe('2')
    fireEvent.change(sl, { target: { value: '' } })
    expect(sl.value).toBe('')            // optional override stays cleared
  })
})
