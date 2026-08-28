import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary'
}

const variants = {
  primary: 'bg-primary text-white hover:bg-primary/90',
  secondary: 'border border-border text-text-muted hover:text-text hover:bg-surface-2',
}

/** Shared button styling (color/weight/rounding/disabled state) — pass layout
 *  classes (flex, gap, padding, flex-1, self-start...) via className. */
export function Button({ variant = 'primary', className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'rounded-lg px-4 py-2 text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
