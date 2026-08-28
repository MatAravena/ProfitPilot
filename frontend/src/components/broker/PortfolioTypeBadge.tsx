import { useTranslation } from 'react-i18next'
import { FlaskConical, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Paper/live status chip — the one place this distinction gets its icon+color treatment,
 *  shared by every page that lists broker connections or strategies. */
export function PortfolioTypeBadge({ isPaper }: { isPaper: boolean }) {
  const { t } = useTranslation()
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
      isPaper ? 'bg-warning/10 text-warning' : 'bg-danger/10 text-danger',
    )}>
      {isPaper
        ? <><FlaskConical size={9} /> {t('settings.badge.paper')}</>
        : <><Zap size={9} /> {t('settings.badge.live')}</>}
    </span>
  )
}
