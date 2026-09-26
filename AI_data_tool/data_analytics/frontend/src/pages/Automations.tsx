/**
 * Automated analysis runs (E12): start one on a dataset, watch its seven
 * steps, answer it when review holds it, stop it or retry a failed step.
 *
 * The runner behind this could already do the whole chain unattended and
 * survive restarts, but nothing in the product could start a run or answer
 * one, and a held run's notification linked nowhere. `?run=<id>` (the link
 * in that notification) opens the run it names.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Workflow } from 'lucide-react'
import { useT, type MessageKey } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import { structuredDetail } from '../lib/friendlyError'
import {
  automationApi, datasetsApi, isAutomationActive,
  type AutomationRunRow, type AutomationStepRow, type Dataset,
} from '../services/api'
import EmptyState from '../components/ui/EmptyState'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'

const STATUS_KEY: Record<AutomationRunRow['status'], MessageKey> = {
  pending: 'auto.status.pending', running: 'auto.status.running', failed: 'auto.status.failed',
  needs_review: 'auto.status.needs_review', done: 'auto.status.done', cancelled: 'auto.status.cancelled',
}
const STATUS_COLOR: Record<AutomationRunRow['status'], string> = {
  pending: 'var(--muted)', running: 'var(--accent)', failed: 'var(--danger, #c0392b)',
  needs_review: '#b45309', done: '#15803d', cancelled: 'var(--muted)',
}
const STEP_KEY: Record<string, MessageKey> = {
  profile: 'auto.step.profile', describe: 'auto.step.describe', scan: 'auto.step.scan',
  propose: 'auto.step.propose', review: 'auto.step.review', compose: 'auto.step.compose',
  notify: 'auto.step.notify',
}
const STEP_MARK: Record<AutomationStepRow['status'], string> = { pending: '○', running: '◐', ok: '●', failed: '✕' }

function when(iso: string | null): string {
  return iso ? localDigits(new Date(iso).toLocaleString()) : '—'
}

export default function Automations() {
  const t = useT()
  const [params] = useSearchParams()
  const focus = Number(params.get('run')) || null
  const [runs, setRuns] = useState<AutomationRunRow[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [chosen, setChosen] = useState('')
  const [starting, setStarting] = useState(false)
  const [open, setOpen] = useState<number | null>(focus)
  const [detail, setDetail] = useState<Record<number, AutomationRunRow>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [reason, setReason] = useState('')

  const load = useCallback(() => automationApi.list().then(r => { setRuns(r); setError(null) }).catch(setError), [])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    datasetsApi.list().then(ds => setDatasets(ds.filter(d => d.mode !== 'directquery'))).catch(() => setDatasets([]))
  }, [])
  // A run moves on its own (one step a minute at most): follow it while any is unfinished.
  const anyActive = useMemo(() => (runs ?? []).some(isAutomationActive), [runs])
  useEffect(() => {
    if (!anyActive) return
    const id = setInterval(() => { void load() }, 5000)
    return () => clearInterval(id)
  }, [anyActive, load])
  useEffect(() => {
    if (open == null) return
    automationApi.get(open).then(r => setDetail(d => ({ ...d, [open]: r }))).catch(() => {})
  }, [open, runs])

  const start = async () => {
    if (!chosen) return
    setStarting(true)
    try {
      const run = await automationApi.start(Number(chosen))
      toast.success(t('auto.started', { name: run.dataset?.name ?? '' }))
      setOpen(run.id)
      await load()
    } catch (e) {
      const d = structuredDetail<{ run_id?: number; message?: string }>(e)
      if (d?.run_id) { toast.error(d.message ?? t('auto.alreadyRunning')); setOpen(d.run_id) }
      else toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('auto.startFailed'))
    } finally {
      setStarting(false)
    }
  }

  const act = async (run: AutomationRunRow, what: 'approve' | 'reject' | 'cancel' | 'retry') => {
    setBusy(run.id)
    try {
      const next = what === 'reject' ? await automationApi.reject(run.id, reason.trim() || undefined)
        : await automationApi[what](run.id)
      setDetail(d => ({ ...d, [run.id]: next }))
      setReason('')
      await load()
    } catch {
      toast.error(t('auto.actionFailed'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <h1 className="dl-page-title" style={{ marginBottom: 6 }}>{t('nav.automations')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 16, maxWidth: 720 }}>{t('auto.intro')}</p>

      <div className="card" style={{ padding: 14, marginBottom: 18, display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, fontWeight: 600 }}>
          {t('auto.dataset')}
          <select value={chosen} onChange={e => setChosen(e.target.value)} style={{ minWidth: 260 }}>
            <option value="">{t('auto.chooseDataset')}</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
        <button className="btn btn-primary btn-sm" disabled={!chosen || starting} onClick={() => void start()}>
          {starting ? t('auto.starting') : t('auto.start')}
        </button>
      </div>

      {runs == null && error == null && <LoadingState />}
      {error != null && <LoadError what="automations" error={error} onRetry={() => void load()} />}
      {runs && runs.length === 0 && (
        <EmptyState icon={Workflow} title={t('auto.emptyTitle')} description={t('auto.emptyBody')} />
      )}

      <div className="dl-rows">
        {(runs ?? []).map(run => {
          const d = detail[run.id] ?? run
          const expanded = open === run.id
          return (
            <div key={run.id} className="dl-rows__row dl-rows__row--stack" data-testid={`run-${run.id}`}
              style={focus === run.id ? { outline: '2px solid var(--accent)', outlineOffset: 2 } : undefined}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <div className="dl-rows__main">
                  <div className="dl-rows__title">
                    {run.dataset ? <Link to={`/datasets/${run.dataset.id}`}>{run.dataset.name}</Link> : t('auto.noDataset')}
                  </div>
                  <div className="dl-rows__meta">{t('auto.startedAt', { when: when(run.created_at) })}</div>
                </div>
                <span data-testid="run-status" style={{ fontSize: 11.5, fontWeight: 700, color: STATUS_COLOR[run.status] }}>
                  {t(STATUS_KEY[run.status])}
                </span>
                <ol aria-label={t('auto.steps')} style={{ display: 'flex', gap: 4, listStyle: 'none', margin: 0, padding: 0 }}>
                  {run.steps.map(s => (
                    <li key={s.name} title={`${t(STEP_KEY[s.name] ?? 'auto.step.profile')}: ${s.status}${s.error ? ` — ${s.error}` : ''}`}
                      aria-label={`${t(STEP_KEY[s.name] ?? 'auto.step.profile')}: ${s.status}`}
                      style={{ fontSize: 13, color: s.status === 'failed' ? 'var(--danger, #c0392b)' : s.status === 'ok' ? '#15803d' : 'var(--muted)' }}>
                      {STEP_MARK[s.status]}
                    </li>
                  ))}
                </ol>
                <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 6 }}>
                  {run.result_report && (
                    <Link className="btn btn-sm" to={`/reports/${run.result_report.id}`}>{t('auto.openReport')}</Link>
                  )}
                  {run.status === 'failed' && (
                    <button className="btn btn-ghost btn-sm" disabled={busy === run.id} onClick={() => void act(run, 'retry')}>{t('auto.retry')}</button>
                  )}
                  {(isAutomationActive(run) || run.status === 'needs_review') && (
                    <button className="btn btn-ghost btn-sm" disabled={busy === run.id} onClick={() => void act(run, 'cancel')}>{t('auto.cancel')}</button>
                  )}
                  <button className="btn btn-ghost btn-sm" aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : run.id)}>{t('auto.details')}</button>
                </span>
              </div>
              {run.summary && <div style={{ fontSize: 12 }}>{run.summary}</div>}
              {run.error && run.status !== 'needs_review' && (
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>{run.error}</div>
              )}

              {run.status === 'needs_review' && (
                <div data-testid="run-decision" style={{ border: '1px solid #b45309', borderRadius: 8, padding: 10, display: 'grid', gap: 8 }}>
                  {run.error && <div style={{ fontSize: 12, fontWeight: 600 }}>{run.error}</div>}
                  <div style={{ fontSize: 12 }}>{(d.widgets_accepted ?? 0) > 0 ? t('auto.decide', {
                    kept: localDigits(String(d.widgets_accepted ?? 0)), rejected: localDigits(String(d.widgets_rejected ?? 0)) })
                    : t('auto.nothingKept')}</div>
                  {(d.rejection_reasons?.length ?? 0) > 0 && (
                    <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 12 }}>
                      {d.rejection_reasons!.map((r, i) => (
                        <li key={i}><b>{r.title || r.widget_type}</b>{r.reason ? ` — ${r.reason}` : ''}</li>
                      ))}
                    </ul>
                  )}
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    {(d.widgets_accepted ?? 0) > 0 && (
                      <button className="btn btn-primary btn-sm" disabled={busy === run.id} onClick={() => void act(run, 'approve')}>{t('auto.approve')}</button>
                    )}
                    <input aria-label={t('auto.rejectReason')} placeholder={t('auto.rejectReason')} value={reason}
                      onChange={e => setReason(e.target.value)} style={{ minWidth: 220 }} />
                    <button className="btn btn-sm" disabled={busy === run.id} onClick={() => void act(run, 'reject')}>{t('auto.reject')}</button>
                  </div>
                </div>
              )}

              {expanded && (
                <table data-testid="run-steps" aria-label={t('auto.steps')} style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
                  <thead><tr>
                    <th style={{ textAlign: 'start', padding: '3px 8px' }}>{t('auto.step')}</th>
                    <th style={{ textAlign: 'start', padding: '3px 8px' }}>{t('auto.state')}</th>
                    <th style={{ textAlign: 'start', padding: '3px 8px' }}>{t('auto.finished')}</th>
                    <th style={{ textAlign: 'start', padding: '3px 8px' }}>{t('auto.note')}</th>
                  </tr></thead>
                  <tbody>
                    {d.steps.map(s => (
                      <tr key={s.name} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: '3px 8px' }}>{t(STEP_KEY[s.name] ?? 'auto.step.profile')}</td>
                        <td style={{ padding: '3px 8px' }}>{s.status}{s.attempts > 1 ? ` (${localDigits(String(s.attempts))})` : ''}</td>
                        <td style={{ padding: '3px 8px' }}>{when(s.finished_at)}</td>
                        <td style={{ padding: '3px 8px', color: s.error ? 'var(--danger, #c0392b)' : 'var(--muted)' }}>
                          {s.error ?? ''}{s.next_attempt_at && s.status === 'failed' ? ` ${t('auto.nextTry', { when: when(s.next_attempt_at) })}` : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
