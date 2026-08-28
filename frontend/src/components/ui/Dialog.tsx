import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { ComponentPropsWithoutRef, HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Dialog = DialogPrimitive.Root

export function DialogContent({ className, ...props }: ComponentPropsWithoutRef<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60" />
      <DialogPrimitive.Content
        className={cn(
          'fixed z-50 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
          'w-full max-w-md mx-4 bg-surface border border-border rounded-xl shadow-2xl focus:outline-none',
          className,
        )}
        {...props}
      />
    </DialogPrimitive.Portal>
  )
}

export function DialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex items-center justify-between px-5 py-4 border-b border-border', className)}
      {...props}
    />
  )
}

export const DialogTitle = DialogPrimitive.Title
export const DialogClose = DialogPrimitive.Close
