import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, TrendingUp, Shield, Zap } from 'lucide-react'

export function Landing() {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const features = [
    { icon: TrendingUp, title: t('landing.features.mlTitle'),     body: t('landing.features.mlBody') },
    { icon: Shield,     title: t('landing.features.riskTitle'),   body: t('landing.features.riskBody') },
    { icon: Zap,        title: t('landing.features.brokerTitle'), body: t('landing.features.brokerBody') },
  ]

  const kpis = [
    { label: t('landing.kpis.drawdown'),   value: '-3.2%',  color: 'text-danger' },
    { label: t('landing.kpis.winRate'),    value: '68%',    color: 'text-success' },
    { label: t('landing.kpis.strategies'), value: '3 live', color: 'text-text' },
  ]

  return (
    <div className="min-h-screen bg-background text-text flex flex-col">
      {/* Nav */}
      <header className="flex items-center justify-between px-8 h-16 border-b border-border">
        <span className="font-bold text-primary tracking-widest text-sm">PROFITPILOT</span>
        <button
          onClick={() => navigate('/dashboard')}
          className="px-4 py-2 text-sm font-medium text-text border border-border rounded-lg hover:border-primary hover:text-primary transition-colors cursor-pointer"
        >
          {t('landing.signIn')}
        </button>
      </header>

      {/* Hero */}
      <section className="flex flex-1 items-center max-w-7xl mx-auto w-full px-8 py-20 gap-16">
        <div className="flex-1 flex flex-col gap-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-primary/10 border border-primary/20 rounded-full w-fit">
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
            <span className="text-xs text-primary font-medium">{t('landing.badge')}</span>
          </div>

          <h1 className="text-5xl font-bold leading-tight tracking-tight">
            {t('landing.headline')}
            <br />
            <span className="text-primary">{t('landing.headlineSub')}</span>
          </h1>

          <p className="text-text-muted text-lg leading-relaxed max-w-md">{t('landing.subtext')}</p>

          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-2 px-6 py-3 bg-accent hover:bg-accent-hover text-white font-semibold rounded-lg transition-colors cursor-pointer"
            >
              {t('landing.getStarted')} <ArrowRight size={16} />
            </button>
            <button className="px-6 py-3 text-text-muted hover:text-text font-medium transition-colors cursor-pointer">
              {t('landing.viewDocs')}
            </button>
          </div>
        </div>

        {/* Live preview mockup */}
        <div className="flex-1 bg-surface border border-border rounded-2xl p-6 shadow-glow">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs text-text-muted font-medium">{t('landing.preview.title')}</span>
            <span className="flex items-center gap-1.5 text-xs text-success">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              {t('landing.preview.connected')}
            </span>
          </div>

          <div className="mb-6">
            <p className="text-3xl font-bold">$124,831.42</p>
            <p className="text-success text-sm mt-1">{t('landing.preview.today')}</p>
          </div>

          <div className="flex items-end gap-1 h-20 mb-6">
            {[40, 55, 48, 62, 58, 72, 65, 78, 71, 85, 80, 92, 88, 95].map((h, i) => (
              <div key={i} className="flex-1 rounded-sm bg-primary/30" style={{ height: `${h}%` }} />
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            {kpis.map(({ label, value, color }) => (
              <div key={label} className="bg-surface-2 rounded-lg p-3">
                <p className="text-[10px] text-text-muted mb-1">{label}</p>
                <p className={`text-sm font-semibold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features strip */}
      <section className="border-t border-border">
        <div className="max-w-7xl mx-auto px-8 py-12 grid grid-cols-3 gap-8">
          {features.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex flex-col gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
                <Icon size={18} className="text-primary" strokeWidth={1.5} />
              </div>
              <h3 className="font-semibold">{title}</h3>
              <p className="text-text-muted text-sm leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
