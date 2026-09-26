import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { formatTimeAgo, useT } from '../i18n'
import { dataflowsApi, datasetsApi, type Dataflow, type Dataset, type DatasetColumn, type PrepStep } from '../services/api'
import PrepPipelinePanel from '../components/report/PrepPipelinePanel'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { useConfirm } from '../components/ui/ConfirmDialog'

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

  const load = () => {
    setLoading(true); setLoadError(null)
    Promise.all([dataflowsApi.list(), datasetsApi.list()])
      .then(([f, d]) => { setFlows(f); setDatasets(d) })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const sources = useMemo(() => datasets.filter(d => d.mode !== 'directquery'), [datasets])
  const nameOf = (id: number | null) => datasets.find(d => d.id === id)?.name ?? `#${id}`
  const open = (id: number | null) => setParams(id ? { flow: String(id) } : {})

  const create = async () => {
    if (!newName.trim() || !newSource) return
    setBusy(true)
    try {
      const flow = await dataflowsApi.create({ name: newName.trim(), source_dataset_id: Number(newSource), steps: [] })
      setNewName(''); setNewSource('')
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
              {sources.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <button className="btn btn-primary btn-sm" disabled={busy || !newName.trim() || !newSource}
            onClick={() => void create()}>{t('flows.create')}</button>
        </div>
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
                  <td>{t(SCHEDULES.find(s => s.minutes === (f.refresh_interval_minutes ?? 0))?.key ?? 'flows.custom',
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

  const setSchedule = async (minutes: number) => {
    try {
      const f = await dataflowsApi.update(flow.id, { refresh_interval_minutes: minutes })
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
            <select value={flow.refresh_interval_minutes ?? 0} disabled={!canEdit}
              onChange={e => void setSchedule(Number(e.target.value))} style={{ width: '100%' }}>
              {SCHEDULES.map(s => <option key={s.minutes} value={s.minutes}>{t(s.key)}</option>)}
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
