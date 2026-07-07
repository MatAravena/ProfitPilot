// Typed API errors + mapping to user-friendly, localized messages.
//
// The backend returns a consistent envelope:
//   { "error": { code, message, details?: { fields? }, traceback? } }
// `request()` in lib/api.ts parses that into an `ApiError`. UI code should catch
// `ApiError` and render `friendlyError(err)` for a human-readable message.

import i18n from '@/i18n'

export interface FieldError {
  field: string
  message: string
  type?: string
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly fields?: FieldError[]

  constructor(code: string, message: string, status: number, fields?: FieldError[]) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.fields = fields
  }
}

/** Known backend error codes (mirror of app/core/errors.py::ErrorCode). */
export const ErrorCode = {
  ValidationError: 'validation_error',
  NotFound: 'not_found',
  BadRequest: 'bad_request',
  UpstreamError: 'upstream_error',
  BacktestFailed: 'backtest_failed',
  InternalError: 'internal_error',
} as const

// Substring patterns (lowercased) mapped to friendly i18n keys. Lets us turn a
// raw backend message into actionable guidance without structured codes for
// every case.
const MESSAGE_PATTERNS: ReadonlyArray<[string, string]> = [
  ['not enough data', 'errors.notEnoughData'],
  ['no data', 'errors.notEnoughData'],
  ['not found', 'errors.symbolNotFound'],
  ['timeframe', 'errors.badTimeframe'],
  ['rate limit', 'errors.rateLimited'],
]

/** Turn any thrown value into a short, localized, user-facing message. */
export function friendlyError(err: unknown): string {
  const t = i18n.t.bind(i18n)

  if (err instanceof ApiError) {
    // Field-level validation → name the first offending field.
    if (err.code === ErrorCode.ValidationError && err.fields?.length) {
      const f = err.fields[0]
      return t('errors.fieldInvalid', { field: f.field || 'input', message: f.message })
    }

    const byPattern = matchPattern(err.message, t)
    if (byPattern) return byPattern

    switch (err.code) {
      case ErrorCode.NotFound:
        return t('errors.notFound')
      case ErrorCode.UpstreamError:
        return t('errors.upstream')
      case ErrorCode.InternalError:
        return t('errors.internal')
      default:
        return err.message || t('errors.generic')
    }
  }

  if (err instanceof Error) {
    return matchPattern(err.message, t) ?? err.message ?? t('errors.generic')
  }
  return t('errors.generic')
}

function matchPattern(message: string, t: typeof i18n.t): string | null {
  const lower = (message || '').toLowerCase()
  for (const [needle, key] of MESSAGE_PATTERNS) {
    if (lower.includes(needle)) return t(key)
  }
  return null
}
