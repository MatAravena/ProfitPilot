import { create } from 'zustand'
import { friendlyError } from '@/lib/errors'

export type ToastKind = 'error' | 'success' | 'info'

export interface Toast {
  id: string
  kind: ToastKind
  message: string
}

interface ToastStore {
  toasts: Toast[]
  push: (kind: ToastKind, message: string, ttl?: number) => string
  dismiss: (id: string) => void
  /** Convenience: turn any thrown value into a localized error toast. */
  error: (err: unknown, ttl?: number) => string
  success: (message: string, ttl?: number) => string
  info: (message: string, ttl?: number) => string
}

const DEFAULT_TTL = 6000

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],

  push: (kind, message, ttl = DEFAULT_TTL) => {
    const id = crypto.randomUUID()
    set((s) => ({ toasts: [...s.toasts, { id, kind, message }] }))
    if (ttl > 0) {
      setTimeout(() => get().dismiss(id), ttl)
    }
    return id
  },

  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  error: (err, ttl) => get().push('error', friendlyError(err), ttl),
  success: (message, ttl) => get().push('success', message, ttl),
  info: (message, ttl) => get().push('info', message, ttl),
}))
