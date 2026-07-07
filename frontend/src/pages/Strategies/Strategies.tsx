import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  TrendingUp, Play, Pause, Trash2, Plus, X,
  ChevronDown, AlertTriangle, FlaskConical, Radio, SlidersHorizontal,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useToastStore } from '@/stores/toast'
import {
  ExecutionConfigForm, DEFAULT_EXECUTION_CONFIG,
} from '@/components/strategy/ExecutionConfigForm'
import type {
  StrategyInstance, StrategyClassDef, CreateStrategyPayload, BrokerConnection, ExecutionConfig,
} from '@/types'

const pct = (f: number) => `${Math.round(f * 1e6) / 1e4}%`

const STATUS_CONFIG: Record<string, { label: string; className: string; icon?: React.ReactNode }> = {
  draft:    { label: 'Draft',
              className: 'bg-surface-2 text-text-muted' },
  paper:    { label: 'Paper',
              className: 'bg-yellow-500/20 text-yellow-400',
              icon: <FlaskConical size={11} /> },
  live:     { label: 'Live',
              className: 'bg-success/20 text-success',
              icon: <Radio size={11} className="animate-pulse" /> },
  paused:   { label: 'Paused',
              className: 'bg-warning/20 text-warning' },
  archived: { label: 'Archived',
              className: 'bg-surface-2 text-text-muted' },
  halted:   { label: 'Halted',
              className: 'bg-danger/20 text-danger',
              icon: <AlertTriangle size={11} /> },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: 'bg-surface-2 text-text-muted' }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${cfg.className}`}>
      {cfg.icon}{cfg.label}
    </span>
  )
}

interface CreateDialogProps {
  classes: StrategyClassDef[]
  brokers: BrokerConnection[]
  onClose: () => void
  onCreate: (payload: CreateStrategyPayload) => void
  isPending: boolean
}

function CreateDialog({ classes, brokers, onClose, onCreate, isPending }: CreateDialogProps) {
  const { t } = useTranslation()
  const [classIdx, setClassIdx] = useState(0)
  const [label, setLabel] = useState('')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1d')
  const [brokerId, setBrokerId] = useState<string>('')
  const [showConfig, setShowConfig] = useState(false)
  const [execution, setExecution] = useState<ExecutionConfig>(DEFAULT_EXECUTION_CONFIG)
  const [params, setParams] = useState<Record<string, number | string>>(() => {
    const defaults: Record<string, number | string> = {}
    classes[0]?.parameters.forEach((p) => { defaults[p.key] = p.default as number | string })
    return defaults
  })

  const selected = classes[classIdx]

  function handleClassChange(idx: number) {
    setClassIdx(idx)
    const defaults: Record<string, number | string> = {}
    classes[idx]?.parameters.forEach((p) => { defaults[p.key] = p.default as number | string })
    setParams(defaults)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onCreate({ class_name: selected.class_name, label, symbol, timeframe, broker_connection_id: brokerId || null, parameters: params, execution })
  }

  function patchExecution(patch: Partial<ExecutionConfig>) {
    setExecution((prev) => ({ ...prev, ...patch }))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-xl w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <span className="text-sm font-semibold text-text">{t('strategies.dialog.title')}</span>
          <button onClick={onClose} className="text-text-muted hover:text-text"><X size={16} /></button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">{t('strategies.dialog.strategy')}</label>
            <div className="relative">
              <select
                value={classIdx} onChange={(e) => handleClassChange(Number(e.target.value))}
                className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text appearance-none pr-8"
              >
                {classes.map((c, i) => <option key={c.class_name} value={i}>{c.display_name}</option>)}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            </div>
            <p className="text-[11px] text-text-muted">{selected?.description}</p>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
              {t('strategies.dialog.label')} <span className="normal-case">{t('strategies.dialog.labelOptional')}</span>
            </label>
            <input
              value={label} onChange={(e) => setLabel(e.target.value)}
              placeholder={selected?.display_name}
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text placeholder:text-text-muted"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">{t('strategies.dialog.symbol')}</label>
              <input
                value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">{t('strategies.dialog.timeframe')}</label>
              <div className="relative">
                <select
                  value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
                  className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text appearance-none pr-8"
                >
                  {['1m','5m','15m','30m','1h','4h','1d','1w'].map((tf) => <option key={tf} value={tf}>{tf}</option>)}
                </select>
                <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
              {t('strategies.dialog.brokerConnection')} <span className="normal-case">{t('strategies.dialog.labelOptional')}</span>
            </label>
            <div className="relative">
              <select
                value={brokerId} onChange={(e) => setBrokerId(e.target.value)}
                className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text appearance-none pr-8"
              >
                <option value="">{t('strategies.dialog.noConnection')}</option>
                {brokers.map((b) => (
                  <option key={b.id} value={b.id}>{b.label || b.broker_id} {b.is_paper ? '(Paper)' : '(Live)'}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            </div>
          </div>

          {selected?.parameters.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">{t('strategies.dialog.parameters')}</label>
              <div className="grid grid-cols-2 gap-2">
                {selected.parameters.map((p) => (
                  <div key={p.key} className="space-y-1">
                    <label className="text-[10px] text-text-muted">{p.label}</label>
                    <input
                      type="number" value={params[p.key] as number ?? p.default}
                      onChange={(e) => setParams((prev) => ({ ...prev, [p.key]: Number(e.target.value) }))}
                      className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm text-text font-mono"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="border-t border-border pt-3">
            <button type="button" onClick={() => setShowConfig((v) => !v)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted uppercase tracking-wider hover:text-text transition-colors">
              <SlidersHorizontal size={12} />
              {t('strategies.config.title')}
              <ChevronDown size={13} className={`transition-transform ${showConfig ? 'rotate-180' : ''}`} />
            </button>
            {showConfig && (
              <div className="mt-3">
                <ExecutionConfigForm value={execution} onChange={patchExecution} />
              </div>
            )}
          </div>

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg border border-border text-sm text-text-muted hover:text-text hover:bg-surface-2 transition-colors">
              {t('strategies.dialog.cancel')}
            </button>
            <button type="submit" disabled={isPending || !symbol}
              className="flex-1 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors">
              {isPending ? t('strategies.dialog.creating') : t('strategies.dialog.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

interface StrategyCardProps {
  strategy: StrategyInstance
  brokers: BrokerConnection[]
  onStatusChange: (id: string, status: string) => void
  onDelete: (id: string) => void
  onEditConfig: (strategy: StrategyInstance) => void
}

function StrategyCard({ strategy, brokers, onStatusChange, onDelete, onEditConfig }: StrategyCardProps) {
  const { t } = useTranslation()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const broker = brokers.find((b) => b.id === strategy.broker_connection_id)
  const canStart = strategy.status === 'draft' || strategy.status === 'paused'
  const canPause = strategy.status === 'paper' || strategy.status === 'live'
  const canGoLive = strategy.status === 'paper'

  return (
    <div className="bg-surface border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-text">{strategy.label}</span>
            <StatusBadge status={strategy.status} />
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-text-muted">
            <span className="font-mono">{strategy.symbol}</span>
            <span>·</span><span>{strategy.timeframe}</span>
            <span>·</span><span>{strategy.class_name}</span>
          </div>
        </div>
        {confirmDelete ? (
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-[10px] text-danger mr-1">{t('strategies.card.deleteConfirm')}</span>
            <button onClick={() => onDelete(strategy.id)}
              className="px-2 py-0.5 rounded text-[10px] font-medium bg-danger/20 text-danger hover:bg-danger/30 transition-colors">
              {t('strategies.card.yes')}
            </button>
            <button onClick={() => setConfirmDelete(false)}
              className="px-2 py-0.5 rounded text-[10px] font-medium bg-surface-2 text-text-muted hover:text-text transition-colors">
              {t('strategies.card.no')}
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={() => onEditConfig(strategy)} title={t('strategies.config.edit')}
              className="text-text-muted hover:text-primary transition-colors">
              <SlidersHorizontal size={14} />
            </button>
            <button onClick={() => setConfirmDelete(true)} className="text-text-muted hover:text-danger transition-colors">
              <Trash2 size={14} />
            </button>
          </div>
        )}
      </div>

      <div className="text-[11px] text-text-muted">
        {broker ? (
          <span>
            {broker.label || broker.broker_id}
            <span className={`ml-1 ${broker.is_paper ? 'text-yellow-400' : 'text-success'}`}>
              ({broker.is_paper ? 'Paper' : 'Live'})
            </span>
          </span>
        ) : (
          <span className="italic">{t('strategies.card.noBroker')}</span>
        )}
      </div>

      {Object.keys(strategy.parameters).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(strategy.parameters).map(([k, v]) => (
            <span key={k} className="text-[10px] bg-surface-2 border border-border px-1.5 py-0.5 rounded font-mono">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {strategy.execution && (
        <div className="flex flex-wrap gap-1.5 text-[10px]">
          <span className="bg-surface-2 border border-border px-1.5 py-0.5 rounded">
            {t('strategies.config.sizeShort')} <span className="font-mono text-text">{pct(strategy.execution.size_pct)}</span>
          </span>
          <span className="bg-surface-2 border border-border px-1.5 py-0.5 rounded">
            {t('strategies.config.slShort')} <span className="font-mono text-danger">{pct(strategy.execution.stop_loss_pct)}</span>
          </span>
          {strategy.execution.take_profit_pct != null && (
            <span className="bg-surface-2 border border-border px-1.5 py-0.5 rounded">
              {t('strategies.config.tpShort')} <span className="font-mono text-success">{pct(strategy.execution.take_profit_pct)}</span>
            </span>
          )}
          {strategy.execution.allow_short && (
            <span className="bg-surface-2 border border-border px-1.5 py-0.5 rounded text-text-muted">
              {t('strategies.config.shortShort')}
            </span>
          )}
        </div>
      )}

      {strategy.error_count > 0 && (
        <div className="flex items-center gap-1 text-[11px] text-danger">
          <AlertTriangle size={11} />
          {t(strategy.error_count === 1 ? 'strategies.card.errors_one' : 'strategies.card.errors_other', { count: strategy.error_count })}
        </div>
      )}

      <div className="flex gap-1.5 pt-1">
        {canStart && (
          <button onClick={() => onStatusChange(strategy.id, 'paper')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-[11px] font-medium hover:bg-yellow-500/20 transition-colors">
            <FlaskConical size={11} /> {t('strategies.card.startPaper')}
          </button>
        )}
        {canGoLive && broker && !broker.is_paper && (
          <button onClick={() => onStatusChange(strategy.id, 'live')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-success/10 border border-success/30 text-success text-[11px] font-medium hover:bg-success/20 transition-colors">
            <Play size={11} /> {t('strategies.card.goLive')}
          </button>
        )}
        {canPause && (
          <button onClick={() => onStatusChange(strategy.id, 'paused')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-surface-2 border border-border text-text-muted text-[11px] font-medium hover:text-text transition-colors">
            <Pause size={11} /> {t('strategies.card.pause')}
          </button>
        )}
      </div>
    </div>
  )
}

interface ConfigDialogProps {
  strategy: StrategyInstance
  onClose: () => void
  onSave: (id: string, cfg: ExecutionConfig) => void
  isPending: boolean
}

function ConfigDialog({ strategy, onClose, onSave, isPending }: ConfigDialogProps) {
  const { t } = useTranslation()
  const [cfg, setCfg] = useState<ExecutionConfig>(strategy.execution ?? DEFAULT_EXECUTION_CONFIG)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-xl w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={14} className="text-primary" />
            <span className="text-sm font-semibold text-text">{t('strategies.config.editTitle')}</span>
            <span className="text-[11px] text-text-muted font-mono">{strategy.label}</span>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          <ExecutionConfigForm value={cfg} onChange={(patch) => setCfg((prev) => ({ ...prev, ...patch }))} />
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg border border-border text-sm text-text-muted hover:text-text hover:bg-surface-2 transition-colors">
              {t('strategies.dialog.cancel')}
            </button>
            <button type="button" disabled={isPending} onClick={() => onSave(strategy.id, cfg)}
              className="flex-1 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors">
              {isPending ? t('strategies.config.saving') : t('strategies.config.save')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function Strategies() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const toastError = useToastStore((s) => s.error)
  const toastSuccess = useToastStore((s) => s.success)
  const [showCreate, setShowCreate] = useState(false)
  const [configTarget, setConfigTarget] = useState<StrategyInstance | null>(null)

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: api.strategies.list,
    refetchInterval: 10_000,
  })

  const { data: classes = [] } = useQuery({
    queryKey: ['strategy-classes'],
    queryFn: api.strategies.classes,
  })

  const { data: brokers = [] } = useQuery({
    queryKey: ['brokers'],
    queryFn: api.brokers.list,
  })

  const createMutation = useMutation({
    mutationFn: api.strategies.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['strategies'] }); setShowCreate(false) },
    onError: (err) => toastError(err),
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.strategies.updateStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
    onError: (err) => toastError(err),
  })

  const configMutation = useMutation({
    mutationFn: ({ id, cfg }: { id: string; cfg: ExecutionConfig }) => api.strategies.updateConfig(id, cfg),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
      setConfigTarget(null)
      toastSuccess(t('strategies.config.saved'))
    },
    onError: (err) => toastError(err),
  })

  const deleteMutation = useMutation({
    mutationFn: api.strategies.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  const active = strategies.filter((s) => s.status === 'paper' || s.status === 'live')
  const inactive = strategies.filter((s) => s.status !== 'paper' && s.status !== 'live')

  return (
    <div className="flex flex-col h-full p-6 gap-6 overflow-y-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text flex items-center gap-2">
            <TrendingUp size={18} className="text-primary" />
            {t('strategies.title')}
          </h1>
          <p className="text-[12px] text-text-muted mt-0.5">{t('strategies.subtitle')}</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus size={14} /> {t('strategies.newStrategy')}
        </button>
      </div>

      {isLoading && <div className="text-sm text-text-muted">{t('strategies.loading')}</div>}

      {active.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
            {t('strategies.running', { count: active.length })}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {active.map((s) => (
              <StrategyCard key={s.id} strategy={s} brokers={brokers}
                onStatusChange={(id, status) => statusMutation.mutate({ id, status })}
                onDelete={(id) => deleteMutation.mutate(id)}
                onEditConfig={setConfigTarget} />
            ))}
          </div>
        </section>
      )}

      {inactive.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
            {t('strategies.inactive', { count: inactive.length })}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {inactive.map((s) => (
              <StrategyCard key={s.id} strategy={s} brokers={brokers}
                onStatusChange={(id, status) => statusMutation.mutate({ id, status })}
                onDelete={(id) => deleteMutation.mutate(id)}
                onEditConfig={setConfigTarget} />
            ))}
          </div>
        </section>
      )}

      {!isLoading && strategies.length === 0 && (
        <div className="flex flex-col items-center justify-center flex-1 gap-3 text-center">
          <TrendingUp size={36} className="text-text-muted opacity-40" />
          <div>
            <p className="text-sm font-medium text-text">{t('strategies.empty')}</p>
            <p className="text-[12px] text-text-muted mt-1">{t('strategies.emptyHint')}</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-2 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus size={14} /> {t('strategies.newStrategy')}
          </button>
        </div>
      )}

      {showCreate && classes.length > 0 && (
        <CreateDialog
          classes={classes} brokers={brokers}
          onClose={() => setShowCreate(false)}
          onCreate={(payload) => createMutation.mutate(payload)}
          isPending={createMutation.isPending}
        />
      )}

      {configTarget && (
        <ConfigDialog
          strategy={configTarget}
          onClose={() => setConfigTarget(null)}
          onSave={(id, cfg) => configMutation.mutate({ id, cfg })}
          isPending={configMutation.isPending}
        />
      )}
    </div>
  )
}
