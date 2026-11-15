import type { StrategyParamDef } from '@/types/backtest'

/** Search space for a one-click walk-forward: each numeric parameter at half, same, and
 * 1.5× its current value. Ints are rounded and kept ≥ 2 (every built-in period needs that);
 * duplicates are dropped. Combos the strategy itself rejects (e.g. fast ≥ slow) are skipped
 * server-side, so this doesn't need to know each strategy's rules. */
export function buildParamGrid(
  defs: StrategyParamDef[],
  current: Record<string, unknown>,
): Record<string, number[]> {
  const grid: Record<string, number[]> = {}
  for (const def of defs) {
    const raw = current[def.key] ?? def.default
    const value = typeof raw === 'number' ? raw : Number(raw)
    if (!Number.isFinite(value)) continue
    const isInt = def.type === 'int'
    const candidates = [value * 0.5, value, value * 1.5].map((v) =>
      isInt ? Math.max(2, Math.round(v)) : Math.round(v * 1000) / 1000,
    )
    grid[def.key] = [...new Set(candidates)].sort((a, b) => a - b)
  }
  return grid
}

export function gridSize(grid: Record<string, number[]>): number {
  return Object.values(grid).reduce((n, values) => n * values.length, 1)
}
