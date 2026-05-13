import { describe, it, expect } from 'vitest'
import { cn, formatCurrency, formatPercent, formatNumber } from './utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('deduplicates tailwind classes (last wins)', () => {
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
  })

  it('filters falsy values', () => {
    expect(cn('a', false && 'b', undefined, 'c')).toBe('a c')
  })
})

describe('formatCurrency', () => {
  it('formats positive value', () => {
    expect(formatCurrency(1234.56)).toBe('$1,234.56')
  })

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('formats negative value', () => {
    expect(formatCurrency(-500)).toBe('-$500.00')
  })

  it('respects custom decimal places', () => {
    expect(formatCurrency(1.5, 0)).toBe('$2')
  })
})

describe('formatPercent', () => {
  it('prefixes positive with +', () => {
    expect(formatPercent(5.5)).toBe('+5.50%')
  })

  it('does not double-prefix negative', () => {
    expect(formatPercent(-3.14)).toBe('-3.14%')
  })

  it('formats zero as +0.00%', () => {
    expect(formatPercent(0)).toBe('+0.00%')
  })

  it('respects custom decimal places', () => {
    expect(formatPercent(1.23456, 1)).toBe('+1.2%')
  })
})

describe('formatNumber', () => {
  it('formats with thousand separators', () => {
    expect(formatNumber(1000000)).toBe('1,000,000.00')
  })

  it('respects custom decimal places', () => {
    expect(formatNumber(3.14159, 3)).toBe('3.142')
  })
})
