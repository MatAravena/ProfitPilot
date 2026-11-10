import { describe, it, expect } from 'vitest'
import en from './locales/en.json'
import es from './locales/es.json'

/** Recursively collect every leaf key path, e.g. "backtests.grid.arm.grid_guarded_reanchor". */
function leafKeys(obj: unknown, prefix = ''): string[] {
  if (typeof obj !== 'object' || obj === null) return [prefix]
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leafKeys(v, prefix ? `${prefix}.${k}` : k)
  )
}

describe('locale parity', () => {
  it('en and es expose exactly the same key paths', () => {
    const enKeys = leafKeys(en).sort()
    const esKeys = leafKeys(es).sort()
    const missingInEs = enKeys.filter((k) => !esKeys.includes(k))
    const missingInEn = esKeys.filter((k) => !enKeys.includes(k))
    expect({ missingInEs, missingInEn }).toEqual({ missingInEs: [], missingInEn: [] })
  })

  it('no translation value is an empty string', () => {
    for (const [name, bundle] of [['en', en], ['es', es]] as const) {
      const empties = leafKeys(bundle).filter((path) => {
        const value = path.split('.').reduce<unknown>(
          (acc, k) => (acc as Record<string, unknown>)?.[k], bundle
        )
        return value === ''
      })
      expect({ [name]: empties }).toEqual({ [name]: [] })
    }
  })

  it('has the grid block wired on both locales', () => {
    expect(leafKeys(en)).toContain('backtests.grid.title')
    expect(leafKeys(es)).toContain('backtests.grid.title')
  })
})
