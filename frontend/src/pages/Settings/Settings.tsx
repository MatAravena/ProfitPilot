import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Trash2, Plus, AlertTriangle, CheckCircle, FlaskConical, Zap, Eye, EyeOff } from 'lucide-react'
import { api } from '@/lib/api'
import type { BrokerName, ConnectBrokerPayload, RiskProfile } from '@/types'
import { useToastStore } from '@/stores/toast'
import { cn } from '@/lib/utils'

const BROKERS: { id: BrokerName; label: string; markets: string }[] = [
  { id: 'bybit',   label: 'Bybit',   markets: 'Crypto · Futures' },
  { id: 'binance', label: 'Binance', markets: 'Crypto · Spot' },
  { id: 'alpaca',  label: 'Alpaca',  markets: 'Stocks · Crypto' },
]

const EMPTY_FORM: ConnectBrokerPayload = {
  broker_id: 'bybit',
  api_key: '',
  secret_key: '',
  label: '',
  is_paper: true,
}

export function Settings() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ConnectBrokerPayload>(EMPTY_FORM)
  const [showSecret, setShowSecret] = useState(false)

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['brokers'],
    queryFn: api.brokers.list,
    staleTime: 30_000,
  })

  const connect = useMutation({
    mutationFn: api.brokers.connect,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['brokers'] })
      qc.invalidateQueries({ queryKey: ['portfolio', 'summary'] })
      setForm(EMPTY_FORM)
      setShowForm(false)
    },
  })

  const disconnect = useMutation({
    mutationFn: (id: string) => api.brokers.disconnect(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['brokers'] })
      qc.invalidateQueries({ queryKey: ['portfolio', 'summary'] })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.api_key.trim() || !form.secret_key.trim()) return
    connect.mutate({
      ...form,
      label: form.label.trim() || `${form.broker_id} ${form.is_paper ? '(paper)' : '(live)'}`,
    })
  }

  return (
    <div className="p-6 flex flex-col gap-6 animate-fade-in max-w-2xl">
      <h1 className="text-lg font-semibold">{t('settings.title')}</h1>

      <RiskDefaults />

      {/* Connected brokers */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wide">{t('settings.connectedBrokers')}</h2>
          {!showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 font-medium transition-colors cursor-pointer"
            >
              <Plus size={14} />
              {t('settings.addBroker')}
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="text-sm text-text-muted">{t('settings.loading')}</div>
        ) : connections.length === 0 && !showForm ? (
          <div className="bg-surface border border-border rounded-xl px-4 py-8 text-center text-text-muted text-sm">
            {t('settings.noBrokers')}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {connections.map((conn) => (
              <div key={conn.id} className="bg-surface border border-border rounded-xl px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold',
                    conn.is_paper ? 'bg-warning/10 text-warning' : 'bg-success/10 text-success',
                  )}>
                    {conn.broker_id.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium capitalize">{conn.broker_id}</span>
                      <PortfolioTypeBadge isPaper={conn.is_paper} />
                    </div>
                    <p className="text-xs text-text-muted">{conn.label}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1 text-xs text-success">
                    <CheckCircle size={12} />
                    <span>{t('settings.active')}</span>
                  </div>
                  <button
                    onClick={() => disconnect.mutate(conn.id)}
                    disabled={disconnect.isPending}
                    className="p-1.5 rounded-lg text-text-muted hover:text-danger hover:bg-danger/10 transition-colors cursor-pointer disabled:opacity-40"
                    title="Disconnect"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Add broker form */}
      {showForm && (
        <section>
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">{t('settings.form.title')}</h2>
          <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-4">

            {/* Broker picker */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('settings.form.broker')}</label>
              <div className="grid grid-cols-3 gap-2">
                {BROKERS.map((b) => (
                  <button
                    key={b.id} type="button"
                    onClick={() => setForm((f) => ({ ...f, broker_id: b.id }))}
                    className={cn(
                      'border rounded-lg p-3 text-left transition-colors cursor-pointer',
                      form.broker_id === b.id ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50',
                    )}
                  >
                    <p className="text-sm font-medium">{b.label}</p>
                    <p className="text-[11px] text-text-muted mt-0.5">{b.markets}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Portfolio type */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('settings.form.portfolioType')}</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button" onClick={() => setForm((f) => ({ ...f, is_paper: true }))}
                  className={cn(
                    'border rounded-lg p-3 text-left transition-colors cursor-pointer',
                    form.is_paper ? 'border-warning bg-warning/10' : 'border-border hover:border-warning/50',
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <FlaskConical size={14} className={form.is_paper ? 'text-warning' : 'text-text-muted'} />
                    <span className={cn('text-sm font-medium', form.is_paper ? 'text-warning' : '')}>
                      {t('settings.form.paper')}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted leading-snug">{t('settings.form.paperDesc')}</p>
                </button>

                <button
                  type="button" onClick={() => setForm((f) => ({ ...f, is_paper: false }))}
                  className={cn(
                    'border rounded-lg p-3 text-left transition-colors cursor-pointer',
                    !form.is_paper ? 'border-danger bg-danger/10' : 'border-border hover:border-danger/50',
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Zap size={14} className={!form.is_paper ? 'text-danger' : 'text-text-muted'} />
                    <span className={cn('text-sm font-medium', !form.is_paper ? 'text-danger' : '')}>
                      {t('settings.form.live')}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted leading-snug">{t('settings.form.liveDesc')}</p>
                </button>
              </div>

              {!form.is_paper && (
                <div className="flex items-start gap-2 bg-danger/10 border border-danger/30 rounded-lg px-3 py-2 mt-1">
                  <AlertTriangle size={14} className="text-danger mt-0.5 shrink-0" />
                  <p className="text-xs text-danger leading-snug">{t('settings.form.liveWarning')}</p>
                </div>
              )}
            </div>

            {/* API Key */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('settings.form.apiKey')}</label>
              <input
                type="text" value={form.api_key}
                onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                placeholder={t('settings.form.apiKeyPlaceholder')}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                required
              />
            </div>

            {/* Secret Key */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('settings.form.secretKey')}</label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'} value={form.secret_key}
                  onChange={(e) => setForm((f) => ({ ...f, secret_key: e.target.value }))}
                  placeholder={t('settings.form.secretKeyPlaceholder')}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 pr-9 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                  required
                />
                <button
                  type="button" onClick={() => setShowSecret((s) => !s)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text cursor-pointer"
                >
                  {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <p className="text-[11px] text-text-muted">{t('settings.form.secretKeyHint')}</p>
            </div>

            {/* Label */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-text-muted font-medium">{t('settings.form.label')}</label>
              <input
                type="text" value={form.label}
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                placeholder={t('settings.form.labelPlaceholder')}
                className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {connect.error && (
              <p className="text-xs text-danger bg-danger/10 rounded-lg px-3 py-2">
                {(connect.error as Error).message}
              </p>
            )}

            <div className="flex gap-2">
              <button
                type="submit" disabled={connect.isPending}
                className="flex-1 bg-primary text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 cursor-pointer"
              >
                {connect.isPending ? t('settings.form.connecting') : t('settings.form.connect')}
              </button>
              <button
                type="button" onClick={() => { setShowForm(false); setForm(EMPTY_FORM) }}
                className="px-4 py-2 border border-border rounded-lg text-sm text-text-muted hover:text-text hover:border-primary/50 transition-colors cursor-pointer"
              >
                {t('settings.form.cancel')}
              </button>
            </div>
          </form>
        </section>
      )}
    </div>
  )
}

const RISK_PCT_FIELDS: { key: keyof RiskProfile; labelKey: string }[] = [
  { key: 'stop_loss_pct', labelKey: 'settings.risk.stopLoss' },
  { key: 'take_profit_pct', labelKey: 'settings.risk.takeProfit' },
  { key: 'max_daily_drawdown_pct', labelKey: 'settings.risk.dailyDrawdown' },
  { key: 'max_total_drawdown_pct', labelKey: 'settings.risk.totalDrawdown' },
]
const RISK_INT_FIELDS: { key: keyof RiskProfile; labelKey: string }[] = [
  { key: 'max_open_positions', labelKey: 'settings.risk.maxPositions' },
  { key: 'max_orders_per_minute', labelKey: 'settings.risk.maxOrdersMin' },
]

function RiskDefaults() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const toastError = useToastStore((s) => s.error)
  const toastSuccess = useToastStore((s) => s.success)
  const [draft, setDraft] = useState<RiskProfile | null>(null)

  const { data } = useQuery({ queryKey: ['risk-profile'], queryFn: api.settings.getRisk })
  const profile = draft ?? data ?? null

  const save = useMutation({
    mutationFn: (body: RiskProfile) => api.settings.updateRisk(body),
    onSuccess: (saved) => {
      qc.setQueryData(['risk-profile'], saved)
      setDraft(null)
      toastSuccess(t('settings.risk.saved'))
    },
    onError: (err) => toastError(err),
  })

  if (!profile) return null
  const set = (patch: Partial<RiskProfile>) => setDraft({ ...profile, ...patch })
  const pctVal = (f: number | null) => (f === null ? '' : String(Math.round(f * 1e6) / 1e4))

  return (
    <section>
      <h2 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">{t('settings.risk.title')}</h2>
      <div className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-4">
        <p className="text-[11px] text-text-muted">{t('settings.risk.hint')}</p>
        <div className="grid grid-cols-2 gap-3">
          {RISK_PCT_FIELDS.map(({ key, labelKey }) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-[11px] text-text-muted">{t(labelKey)}</span>
              <div className="relative">
                <input type="text" inputMode="decimal"
                  value={pctVal(profile[key] as number | null)}
                  placeholder={key === 'take_profit_pct' ? t('settings.risk.none') : ''}
                  onChange={(e) => {
                    const raw = e.target.value
                    const optional = key === 'take_profit_pct'
                    if (raw === '') return set({ [key]: optional ? null : profile[key] } as Partial<RiskProfile>)
                    const n = Number(raw)
                    if (!Number.isNaN(n)) set({ [key]: n / 100 } as Partial<RiskProfile>)
                  }}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 pr-6 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary" />
                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-text-muted">%</span>
              </div>
            </label>
          ))}
          {RISK_INT_FIELDS.map(({ key, labelKey }) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-[11px] text-text-muted">{t(labelKey)}</span>
              <input type="text" inputMode="numeric"
                value={String(profile[key] ?? '')}
                onChange={(e) => {
                  const raw = e.target.value
                  if (raw === '') return
                  const n = Number(raw)
                  if (!Number.isNaN(n)) set({ [key]: Math.trunc(n) } as Partial<RiskProfile>)
                }}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary" />
            </label>
          ))}
        </div>
        <button
          onClick={() => save.mutate(profile)}
          disabled={save.isPending || draft === null}
          className="self-start bg-primary text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 cursor-pointer"
        >
          {save.isPending ? t('settings.risk.saving') : t('settings.risk.save')}
        </button>
      </div>
    </section>
  )
}

function PortfolioTypeBadge({ isPaper }: { isPaper: boolean }) {
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
