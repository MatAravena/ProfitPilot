import { forwardRef } from 'react'
import type { SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  wrapperClassName?: string
}

/** Styled native <select> — kept native (not Radix) so existing tests can keep using
 *  userEvent.selectOptions()/fireEvent.change() untouched. */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, wrapperClassName, children, ...props }, ref) => (
    <div className={cn('relative', wrapperClassName)}>
      <select
        ref={ref}
        className={cn(
          'appearance-none bg-background border border-border rounded-lg text-text cursor-pointer',
          'focus:outline-none focus:ring-1 focus:ring-primary',
          className,
          'pr-8',
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        size={14}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
      />
    </div>
  ),
)
Select.displayName = 'Select'
