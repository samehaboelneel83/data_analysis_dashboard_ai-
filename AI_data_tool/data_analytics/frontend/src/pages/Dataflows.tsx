import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { formatTimeAgo, useT } from '../i18n'
import { dataflowsApi, datasetsApi, type Dataflow, type DataflowSnapshot, type Dataset, type DatasetColumn, type PrepStep } from '../services/api'
import PrepPipelinePanel from '../components/report/PrepPipelinePanel'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { useConfirm } from '../components/ui/ConfirmDialog'
import DatasetListFilter, { useCleanDatasets } from '../components/dataset/DatasetListFilter'

/**
 * Dataflows (E12): a recipe that reads one dataset, transforms it, and keeps
 * the result as datasets of its own, refreshed on a schedule.
 *
 * The API existed (create, edit, run, schedule, capabilities, delete) and the
 * scheduler ran dataflows, but nothing in the app could make or change one:
 * Monitoring listed their runs with no page to open. The recipe is edited
 * with the same pipeline editor as a dataset's view, previewed over the
 * flow's source.
 */

const SCHEDULES: { minutes: number; key: 'flows.scheduleOff' | 'flows.hourly' | 'flows.daily' | 'flows.weekly' }[] = [
  { minutes: 0, key: 'flows.scheduleOff' }, { minutes: 60, key: 'flows.hourly' },
  { minutes: 1440, key: 'flows.daily' }, { minutes: 10080, key: 'flows.weekly' },
]

/** The schedule choice "after its source refreshes" (pipeline phase 4). */
const AFTER_SOURCE = -1

const detail = (e: unknown, fallback: string) =>
  (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback

export default function Dataflows() {
  const t = useT()
  const confirm = useConfirm()
  const [params, setParams] = useSearchParams()
  const openId = Number(params.get('flow')) || null
  const [flows, setFlows] = useState<Dataflow[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [newName, setNewName] = useState('')
  const [newSource, setNewSource] = useState('')
  const [busy, setBusy] = useState(false)
  // 4.6: "Monthly snapshot" -- a history from a source that only shows today.
  const [kind, setKind] = useState<'transform' | 'snapshot'>('transform')
  const [srcCols, setSrcCols] = useState<string[]>([])
  const [snapGroup, setSnapGroup] = useState('')
  const [snapCount, setSnapCount] = useState('')   // '' = rows, else distinct of this column
  const [snapAs, setSnapAs] = useState('headcount')
  const [snapBackfill, setSnapBackfill] = useState(false)
  const [bfFrom, setBfFrom] = useState('')
  const [bfTo, setBfTo] = useState('')
  const [bfStart, setBfStart] = useState(`${new Date().getFullYear() - 1}-01-01`)
  useEffect(() => {
    if (!newSource) { setSrcCols([]); return }
    let live = true
    datasetsApi.get(Number(newSource)).then(d => {
      if (!live) return
      const cols = (d.columns ?? []).map(c => c.name)
      setSrcCols(cols)
      setBfFrom(cols.find(c => /^(from|start|valid_from|hire)_?(date|dt)?$/i.test(c)) ?? '')
      setBfTo(cols.find(c => /^(to|end|valid_to|until)_?(date|dt)?$/i.test(c)) ?? '')
    }).catch(() => { if (live) setSrcCols([]) })
    return () => { live = false }
  }, [newSource])

  const load = () => {
    setLoading(true); setLoadError(null)
    Promise.all([dataflowsApi.list(), datasetsApi.list()])
      .then(([f, d]) => { setFlows(f); setDatasets(d) })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // Live datasets feed dataflows too (4.6) -- a snapshot of one is the point.
  // 4.7: certified first, test-looking leftovers out of sight.
  const clean = useCleanDatasets(datasets)
  const sources = clean.visible
  const nameOf = (id: number | null) => datasets.find(d => d.id === id)?.name ?? `#${id}`
  const open = (id: number | null) => setParams(id ? { flow: String(id) } : {})

  const create = async () => {
    if (!newName.trim() || !newSource) return
    setBusy(true)
    try {
      const snapshot: DataflowSnapshot | null = kind === 'snapshot' ? {
        every: 'month', group_by: snapGroup ? [snapGroup] : [],
        measure: snapCount || null, agg: snapCount ? 'nunique' : 'count', as: snapAs.trim() || 'headcount',
        backfill: snapBackfill && bfFrom && bfTo ? { from_column: bfFrom, to_column: bfTo, start: bfStart } : null,
      } : null
      const flow = await dataflowsApi.create({ name: newName.trim(), source_dataset_id: Number(newSource), steps: [],
        ...(snapshot ? { snapshot, refresh_interval_minutes: 1440 } : {}) })
      setNewName(''); setNewSource(''); setKind('transform')
      setFlows(fs => [flow, ...fs])
      open(flow.id)
    } catch (e) {
      toast.error(detail(e, t('flows.createFailed')))
    } finally { setBusy(false) }
  }

  if (loading) return <LoadingState />
  if (loadError) return <LoadError what={t('flows.loadWhat')} error={loadError} onRetry={load} />
  const current = flows.find(f => f.id === openId) ?? null

  const lastRun = (f: Dataflow) => {
    if (!f.last_run_at) return t('flows.never')
    const ago = formatTimeAgo(f.last_run_at, t) ?? ''
    if (f.last_run_status === 'ok') return t('flows.ok', { rows: (f.last_run_rows ?? 0).toLocaleString(), ago })
    if (f.last_run_status === 'failed') return t('flows.failed', { ago, error: f.last_run_error ?? '' })
    return t('flows.skipped', { ago })
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.dataflows')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>{t('flows.lead')}</p>

      <section className="card" style={{ padding: 16, marginTop: 16 }} aria-labelledby="new-flow">
        <h2 id="new-flow" style={{ fontSize: 15, marginTop: 0 }}>{t('flows.new')}</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ fontSize: 13 }}>
            <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.name')}</span>
            <input value={newName} onChange={e => setNewName(e.target.value)} style={{ minWidth: 240 }} />
          </label>
          <label style={{ fontSize: 13 }}>
            <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.source')}</span>
            <select value={newSource} onChange={e => setNewSource(e.target.value)} style={{ minWidth: 240 }}>
              <option value="">{t('flows.pickSource')}</option>
              {sources.map(d => <option key={d.id} value={d.id}>{d.name}{d.mode === 'directquery' ? ` · ${t('datasets.live')}` : ''}</option>)}
            </select>
          </label>
          <DatasetListFilter state={clean} />
          <fieldset style={{ border: 'none', padding: 0, margin: 0, fontSize: 13, display: 'flex', gap: 10 }}>
            <legend style={{ fontWeight: 600, marginBottom: 4, padding: 0 }}>{t('flows.kind')}</legend>
            <label><input type="radio" name="flow-kind" checked={kind === 'transform'} onChange={() => setKind('transform')} /> {t('flows.kindTransform')}</label>
            <label><input type="radio" name="flow-kind" checked={kind === 'snapshot'} onChange={() => setKind('snapshot')} /> {t('flows.kindSnapshot')}</label>
          </fieldset>
          <button className="btn btn-primary btn-sm" disabled={busy || !newName.trim() || !newSource}
            onClick={() => void create()}>{t('flows.create')}</button>
        </div>
        {kind === 'snapshot' && (
          <div data-testid="snapshot-form" style={{ marginTop: 12, display: 'grid', gap: 8, fontSize: 13 }}>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12.5 }}>{t('flows.snapshotLead')}</p>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <label>
                <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.snapCount')}</span>
                <select value={snapCount} onChange={e => setSnapCount(e.target.value)}>
                  <option value="">{t('flows.snapRows')}</option>
                  {srcCols.map(c => <option key={c} value={c}>{t('flows.snapDistinct', { col: c })}</option>)}
                </select>
              </label>
              <label>
                <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.snapGroup')}</span>
                <select value={snapGroup} onChange={e => setSnapGroup(e.target.value)}>
                  <option value="">{t('flows.snapNoGroup')}</option>
                  {srcCols.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label>
                <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.snapAs')}</span>
                <input value={snapAs} onChange={e => setSnapAs(e.target.value)} style={{ width: 140 }} />
              </label>
            </div>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="checkbox" checked={snapBackfill} onChange={e => setSnapBackfill(e.target.checked)} />
              {t('flows.snapBackfill')}
            </label>
            {snapBackfill && (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <label><span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.bfFrom')}</span>
                  <select value={bfFrom} onChange={e => setBfFrom(e.target.value)}>
                    <option value="">—</option>{srcCols.map(c => <option key={c} value={c}>{c}</option>)}
                  </select></label>
                <label><span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.bfTo')}</span>
                  <select value={bfTo} onChange={e => setBfTo(e.target.value)}>
                    <option value="">—</option>{srcCols.map(c => <option key={c} value={c}>{c}</option>)}
                  </select></label>
                <label><span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.bfStart')}</span>
                  <input type="date" value={bfStart} onChange={e => setBfStart(e.target.value)} /></label>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card dl-table-card" style={{ marginTop: 16 }}>
        {flows.length === 0 ? (
          <p style={{ padding: 16, color: 'var(--muted)', fontSize: 13, margin: 0 }}>{t('flows.empty')}</p>
        ) : (
          <table className="dl-table">
            <thead>
              <tr>
                <th>{t('flows.name')}</th><th>{t('flows.source')}</th><th>{t('flows.schedule')}</th>
                <th>{t('flows.lastRun')}</th><th>{t('flows.outputs')}</th>
              </tr>
            </thead>
            <tbody>
              {flows.map(f => (
                <tr key={f.id} data-selected={f.id === openId || undefined} data-testid={`flow-${f.id}`}>
                  <td>
                    <button className="btn btn-ghost btn-sm row-name" style={{ padding: 0 }} onClick={() => open(f.id)}>
                      {f.name}
                    </button>
                    <div className="dl-cell-sub">{t('flows.steps', { n: f.steps.length })}</div>
                  </td>
                  <td>{f.source_dataset_id ? <Link to={`/datasets/${f.source_dataset_id}`}>{nameOf(f.source_dataset_id)}</Link> : '—'}</td>
                  <td>{f.run_after_source ? t('flows.afterSource')
                    : t(SCHEDULES.find(s => s.minutes === (f.refresh_interval_minutes ?? 0))?.key ?? 'flows.custom',
                      { n: f.refresh_interval_minutes ?? 0 })}</td>
                  <td className={f.last_run_status === 'failed' ? 'dl-fresh--bad' : undefined}>{lastRun(f)}</td>
                  <td>
                    {f.outputs.length === 0 ? <span style={{ color: 'var(--muted)' }}>{t('flows.noOutputs')}</span>
                      : f.outputs.map((o, i) => (
                        <span key={o.id}>{i > 0 && ', '}<Link to={`/datasets/${o.id}`}>{o.name}</Link></span>
                      ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {current && (
        <FlowEditor key={current.id} flow={current} datasets={datasets}
          onChanged={updated => setFlows(fs => fs.map(f => f.id === updated.id ? { ...f, ...updated } : f))}
          onDeleted={() => { setFlows(fs => fs.filter(f => f.id !== current.id)); open(null) }}
          onReload={load} confirm={confirm} />
      )}
    </div>
  )
}

function FlowEditor({ flow, datasets, onChanged, onDeleted, onReload, confirm }: {
  flow: Dataflow; datasets: Dataset[]
  onChanged: (f: Dataflow) => void; onDeleted: () => void; onReload: () => void
  confirm: ReturnType<typeof useConfirm>
}) {
  const t = useT()
  const [columns, setColumns] = useState<DatasetColumn[] | null>(null)
  const [outputName, setOutputName] = useState('')
  const [running, setRunning] = useState(false)
  const canEdit = flow.your_capability === 'edit' || flow.your_capability === 'data'
  const canDelete = flow.your_capability === 'data'

  useEffect(() => {
    if (!flow.source_dataset_id) { setColumns([]); return }
    let live = true
    datasetsApi.get(flow.source_dataset_id)
      .then(d => { if (live) setColumns(d.columns ?? []) })
      .catch(() => { if (live) setColumns([]) })
    return () => { live = false }
  }, [flow.source_dataset_id])

  const saveSteps = async (steps: PrepStep[]) => {
    try {
      const f = await dataflowsApi.update(flow.id, { steps: steps as Record<string, unknown>[] })
      onChanged({ ...flow, ...f, outputs: flow.outputs })
      toast.success(t('flows.saved'))
    } catch (e) {
      toast.error(detail(e, t('flows.saveFailed')))
    }
  }

  /** -1 = after the source refreshes (phase 4); 0 = off; else a timer. */
  const setSchedule = async (minutes: number) => {
    try {
      const f = await dataflowsApi.update(flow.id, minutes === AFTER_SOURCE
        ? { run_after_source: true }
        : { refresh_interval_minutes: minutes, ...(minutes === 0 ? { run_after_source: false } : {}) })
      onChanged({ ...flow, ...f, outputs: flow.outputs })
    } catch (e) {
      toast.error(detail(e, t('flows.saveFailed')))
    }
  }

  const run = async (name?: string) => {
    setRunning(true)
    try {
      const r = await dataflowsApi.run(flow.id, name)
      toast.success(t('flows.ran', { rows: r.rows.toLocaleString() }))
      setOutputName('')
      onReload()
    } catch (e) {
      toast.error(detail(e, t('flows.runFailed')))
      onReload()
    } finally { setRunning(false) }
  }

  const remove = async () => {
    if (!await confirm({ title: t('flows.deleteTitle', { name: flow.name }), body: t('flows.deleteBody') })) return
    try {
      await dataflowsApi.remove(flow.id)
      onDeleted()
    } catch (e) {
      toast.error(detail(e, t('flows.deleteFailed')))
    }
  }

  const source = datasets.find(d => d.id === flow.source_dataset_id)
  return (
    <section className="card" style={{ padding: 16, marginTop: 16 }} aria-labelledby="flow-editor">
      <h2 id="flow-editor" style={{ fontSize: 15, marginTop: 0 }}>{flow.name}</h2>
      {!canEdit && <p role="note" style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t('flows.viewOnly')}</p>}
      {flow.snapshot && (
        <p data-testid="snapshot-summary" style={{ fontSize: 12.5, marginTop: 0 }}>
          {t('flows.snapSummary', {
            what: flow.snapshot.measure ? t('flows.snapDistinct', { col: flow.snapshot.measure }) : t('flows.snapRows'),
            by: flow.snapshot.group_by?.length ? flow.snapshot.group_by.join(', ') : t('flows.snapNoGroup'),
            as: flow.snapshot.as ?? 'rows' })}
          {flow.snapshot.backfill ? ` ${t('flows.snapBackfilled', { start: flow.snapshot.backfill.start })}` : ''}
        </p>
      )}

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 380px', minWidth: 0 }}>
          <h3 style={{ fontSize: 13, margin: '0 0 8px' }}>{t('flows.recipe')}</h3>
          {columns === null ? <LoadingState /> : (
            <PrepPipelinePanel datasetId={flow.source_dataset_id ?? 0} columns={columns}
              datasetName={source?.name} initialSteps={flow.steps as PrepStep[]}
              onSave={saveSteps} saveLabel={t('flows.saveRecipe')} readOnly={!canEdit} />
          )}
        </div>
        <div style={{ flex: '0 1 300px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ fontSize: 13 }}>
            <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.schedule')}</span>
            <select value={flow.run_after_source ? AFTER_SOURCE : flow.refresh_interval_minutes ?? 0} disabled={!canEdit}
              onChange={e => void setSchedule(Number(e.target.value))} style={{ width: '100%' }}>
              {SCHEDULES.map(s => <option key={s.minutes} value={s.minutes}>{t(s.key)}</option>)}
              {flow.source_dataset_id != null && <option value={AFTER_SOURCE}>{t('flows.afterSource')}</option>}
              {flow.refresh_interval_minutes && !SCHEDULES.some(s => s.minutes === flow.refresh_interval_minutes) && (
                <option value={flow.refresh_interval_minutes}>{t('flows.custom', { n: flow.refresh_interval_minutes })}</option>
              )}
            </select>
          </label>
          {canEdit && (
            <>
              <button className="btn btn-sm" disabled={running || flow.outputs.length === 0}
                title={flow.outputs.length === 0 ? t('flows.noOutputsHint') : undefined}
                onClick={() => void run()}>{t('flows.refresh')}</button>
              <label style={{ fontSize: 13 }}>
                <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('flows.outputName')}</span>
                <input value={outputName} onChange={e => setOutputName(e.target.value)} style={{ width: '100%' }} />
              </label>
              <button className="btn btn-primary btn-sm" disabled={running || !outputName.trim()}
                onClick={() => void run(outputName.trim())}>{t('flows.runNew')}</button>
            </>
          )}
          {canDelete && (
            <button className="btn btn-sm btn-danger" onClick={() => void remove()}>{t('flows.delete')}</button>
          )}
        </div>
      </div>
    </section>
  )
}
