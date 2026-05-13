import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Briefcase, TrendingUp, Settings, FlaskConical, Code2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui'
import { useWebSocketStore } from '@/stores/websocket'

export function Sidebar() {
  const { t, i18n } = useTranslation()
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const wsStatus = useWebSocketStore((s) => s.status)

  const NAV_ITEMS = [
    { to: '/dashboard',  icon: LayoutDashboard, label: t('nav.dashboard') },
    { to: '/portfolio',  icon: Briefcase,        label: t('nav.portfolio') },
    { to: '/backtests',  icon: FlaskConical,     label: t('nav.backtest') },
    { to: '/strategies', icon: TrendingUp,       label: t('nav.strategies') },
    { to: '/builder',    icon: Code2,            label: t('nav.builder') },
  ]

  function toggleLang() {
    i18n.changeLanguage(i18n.language === 'es' ? 'en' : 'es')
  }

  return (
    <aside
      className={cn(
        'flex flex-col h-full bg-surface border-r border-border transition-all duration-200',
        collapsed ? 'w-14' : 'w-[110px]',
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-center h-14 border-b border-border shrink-0">
        <span className="text-primary font-bold text-sm tracking-widest">
          {collapsed ? 'PP' : 'PROFITPILOT'}
        </span>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 p-2 flex-1">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex flex-col items-center gap-1 px-2 py-3 rounded-lg transition-colors cursor-pointer',
                'text-text-muted hover:text-text hover:bg-surface-2',
                isActive && 'text-primary bg-primary/10',
              )
            }
          >
            <Icon size={18} strokeWidth={1.5} />
            {!collapsed && <span className="text-[10px] font-medium tracking-wide">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-border flex flex-col items-center gap-2">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              'flex flex-col items-center gap-1 px-2 py-3 rounded-lg transition-colors cursor-pointer w-full',
              'text-text-muted hover:text-text hover:bg-surface-2',
              isActive && 'text-primary bg-primary/10',
            )
          }
        >
          <Settings size={18} strokeWidth={1.5} />
          {!collapsed && <span className="text-[10px] font-medium tracking-wide">{t('nav.settings')}</span>}
        </NavLink>

        {/* Language toggle */}
        <button
          onClick={toggleLang}
          title="Toggle language"
          className="text-[10px] font-bold text-text-muted hover:text-primary transition-colors cursor-pointer tracking-wider"
        >
          {i18n.language === 'es' ? 'EN' : 'ES'}
        </button>

        {/* WS status dot */}
        <div className={cn('w-1.5 h-1.5 rounded-full', {
          'bg-success': wsStatus === 'connected',
          'bg-warning animate-pulse': wsStatus === 'connecting',
          'bg-danger': wsStatus === 'error' || wsStatus === 'disconnected',
        })} />
      </div>
    </aside>
  )
}
