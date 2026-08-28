import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

/** Shared surface/border/rounding shell — pass padding/layout classes via className. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('bg-surface border border-border rounded-xl', className)} {...props} />
}
