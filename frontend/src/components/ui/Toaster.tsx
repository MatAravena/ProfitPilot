import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { useToastStore, type ToastKind } from '@/stores/toast'

const ICONS: Record<ToastKind, typeof AlertCircle> = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
}

const ACCENT: Record<ToastKind, string> = {
  error: 'border-l-danger text-danger',
  success: 'border-l-success text-success',
  info: 'border-l-primary text-primary',
}

/** Global toast outlet. Mount once near the app root. */
export function Toaster() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  if (!toasts.length) return null

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
      {toasts.map((t) => {
        const Icon = ICONS[t.kind]
        return (
          <div
            key={t.id}
            role="alert"
            className={`pointer-events-auto flex items-start gap-2.5 rounded-lg border border-l-4 border-border bg-surface px-3.5 py-3 shadow-lg ${ACCENT[t.kind]}`}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="flex-1 text-sm leading-snug text-text">{t.message}</p>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 rounded p-0.5 text-text-muted hover:text-text cursor-pointer"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
