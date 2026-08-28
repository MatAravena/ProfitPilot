import { ChevronLeft, ChevronRight } from 'lucide-react'

interface PaginationButtonsProps {
  onPrev: () => void
  onNext: () => void
  prevDisabled: boolean
  nextDisabled: boolean
  prevLabel: string
  nextLabel: string
}

const btnCls =
  'p-1 rounded border border-border hover:bg-surface-2 disabled:opacity-40 disabled:hover:bg-transparent transition-colors'

/** Prev/next chevron buttons shared by every paginated table/list in the app. */
export function PaginationButtons({ onPrev, onNext, prevDisabled, nextDisabled, prevLabel, nextLabel }: PaginationButtonsProps) {
  return (
    <>
      <button type="button" onClick={onPrev} disabled={prevDisabled} className={btnCls} aria-label={prevLabel}>
        <ChevronLeft size={14} />
      </button>
      <button type="button" onClick={onNext} disabled={nextDisabled} className={btnCls} aria-label={nextLabel}>
        <ChevronRight size={14} />
      </button>
    </>
  )
}
