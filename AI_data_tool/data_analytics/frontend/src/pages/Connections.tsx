import { useEffect, useState } from 'react'
import LoadError from '../components/ui/LoadError'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useOptionalAuth } from '../contexts/AuthContext'
import { dataSourcesApi, datasetsApi, metadataApi, setupApi } from '../services/api'
import type { DataSource, ConnectorSpec, SetupJourney, SyncRun } from '../services/api'
import { localDigits } from '../lib/arabicFormats'
import toast from 'react-hot-toast'
import { useConfirm } from '../components/ui/ConfirmDialog'
import QueryBuilderDialog from '../components/QueryBuilderDialog'
import ImportQueue from '../components/jobs/ImportQueue'
import {
  Cable, Code2, Compass, Database, Info, Loader2, Pencil, PlugZap,
  Plus, ScanSearch, Table2, Trash2, Upload,
} from 'lucide-react'
import { formatTimeAgo } from '../i18n'
import FilterChip from './lineage/FilterChip'
import './connections/connections.css'
import ActionMenu from '../components/ActionMenu'
import { useListFilter } from '../components/ui/ListFilter'
import { useT } from '../i18n'

import { TYPE_ICON, TYPE_LABEL } from './connections/typeMaps'
import { ConnectionModal } from './connections/ConnectionModal'
import CombineDialog from './connections/CombineDialog'
import { SchemaBrowser } from './connections/SchemaBrowser'
export { SchemaBrowser } from './connections/SchemaBrowser'

/* ── Main Connections Page ─────────────────────────────── */
export default function Connections() {
  const t = useT()
  const [sources,  setSources]  = useState<DataSource[]>([])
  // Guided setup: where this person stopped on each connection ("Continue setup").
  const [journeys, setJourneys] = useState<Record<number, SetupJourney>>({})
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  // The search every list page shares (one box, one rule); the type filter narrows what it finds.
  const srcFilter = useListFilter(sources, d => [d.name, d.type, TYPE_LABEL[d.type] ?? ''], t('cn2.search'), { always: true })
  // Per connection: its last metadata sync (the status and "Last sync" the
  // list shows without testing), and how many datasets read from it.
  const [syncs, setSyncs] = useState<Record<number, SyncRun>>({})
  const [datasetCount, setDatasetCount] = useState<Record<number, number>>({})
  const [catalog,  setCatalog]  = useState<ConnectorSpec[]>([])
  const [loading,  setLoading]  = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal,    setModal]    = useState<'add' | DataSource | null>(null)
  const [combining, setCombining] = useState(false)
  // Non-throwing: this page is mounted in harnesses without the provider, and
  // no auth means no admin -- failing CLOSED, which shows the read-only view
  // rather than a row of buttons the server would refuse.
  const user = useOptionalAuth()?.user
  /** The API refuses connection administration to anyone who is neither an
   *  org admin nor the person who added the connection (`_may_administer` in
   *  routers/data_sources.py). This mirrors the admin half of that rule; the
   *  server remains the enforcement, exactly as `RequireAdmin` documents. */
  const canAdminister = !!user?.role?.is_org_admin
  // The row menu navigates to the metadata review, where a <Link> used to sit.
  const goTo = useNavigate()
  const [browser,  setBrowser]  = useState<DataSource | null>(null)
  const [building, setBuilding] = useState<DataSource | null>(null)
  // Guided setup "Build it myself": ?browse=<id> opens the schema browser and
  // ?build=<id> the query builder for that connection, once the list is in.
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    const browse = Number(params.get('browse')), build = Number(params.get('build'))
    if (!sources.length || (!browse && !build) || !canAdminister) return
    const ds = sources.find(s => s.id === (browse || build))
    if (ds) { if (browse) setBrowser(ds); else setBuilding(ds) }
    setParams({}, { replace: true })
  }, [sources, params, canAdminister, setParams])
  // Bumped when the schema browser queues an import, so the Imports list
  // shows it without waiting for its next poll.
  const [queueKey, setQueueKey] = useState(0)
  const [testing,  setTesting]  = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, boolean | null>>({})
  // Why a test failed stays on the row: the toast that said so vanished in
  // seconds and the badge alone read only "Failed" (role tour, 2026-10-10).
  const [testErrors, setTestErrors] = useState<Record<number, string>>({})

  useEffect(() => {
    // Without the catch, a server error cleared `loading` and fell through to
    // "No connections yet" -- a claim about the user's estate rather than about
    // our ability to read it.
    setLoadError(null)
    dataSourcesApi.list().then(list => {
      setSources(list)
      for (const ds of list) {
        Promise.resolve(metadataApi.latestSync?.(ds.id))
          .then(run => { if (run) setSyncs(m => ({ ...m, [ds.id]: run })) }).catch(() => {})
      }
    })
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
    Promise.resolve(datasetsApi.list?.()).then(ds => {
      const n: Record<number, number> = {}
      for (const d of ds ?? []) if (d.data_source_id != null) n[d.data_source_id] = (n[d.data_source_id] ?? 0) + 1
      setDatasetCount(n)
    }).catch(() => {})
    // Fetch the connector catalog and populate the icon/label maps in place so
    // list rows and the schema browser render a friendly name for any type.
    // Optional: without it every row still offers to start the setup.
    Promise.resolve(setupApi.journeys?.()).then(js => {
      if (js) setJourneys(Object.fromEntries(js.map(j => [j.source.id, j])))
    }).catch(() => {})
    dataSourcesApi.connectors().then(specs => {
      setCatalog(specs)
      for (const s of specs) { TYPE_ICON[s.key] = s.icon; TYPE_LABEL[s.key] = s.label }
    }).catch(() => {})
  }, [])

  const handleSaved = (ds: DataSource) => {
    const isNew = !sources.some(s => s.id === ds.id)
    setSources(prev => {
      const idx = prev.findIndex(s => s.id === ds.id)
      return idx >= 0 ? prev.map(s => s.id === ds.id ? ds : s) : [ds, ...prev]
    })
    setModal(null)
    // A NEW connection goes straight to the page that explains it, where the
    // sync the create just started is already running. Before this, creating a
    // connection showed a toast and left the person looking at a list of table
    // names -- the overview, the descriptions and the inferred joins all sat
    // behind a sync nothing prompted them to run, reachable only from a row
    // menu they had no reason to open.
    //
    // Only when a sync actually started: with no run to watch, the review page
    // is an empty queue and the list is the more useful place to be.
    //
    // Guided setup (docs/guided-setup/PLAN.md): that page is now the setup's
    // first step, which explains the source in plain words and waits for the
    // sync itself -- so it is where every new connection goes.
    if (isNew) goTo(`/setup/${ds.id}`)
  }

  const confirm = useConfirm()
  const handleDelete = async (ds: DataSource) => {
    if (!await confirm({ title: t('bc.dialogs.deleteNamed', { name: ds.name }), body: t('bc.dialogs.cannotUndo') })) return
    await dataSourcesApi.delete(ds.id)
    setSources(prev => prev.filter(s => s.id !== ds.id))
    toast.success(t('bc.dialogs.deleted'))
  }

  const handleTest = async (ds: DataSource) => {
    setTesting(ds.id)
    setTestResults(p => ({ ...p, [ds.id]: null }))
    try {
      const r = await dataSourcesApi.test(ds.id)
      setTestResults(p => ({ ...p, [ds.id]: r.ok }))
      setTestErrors(p => ({ ...p, [ds.id]: r.ok ? '' : (r.error ?? t('pg.dataPages.conn.connectionFailed')) }))
      if (r.ok) toast.success(t('pg.dataPages.conn.connectedToast', { name: ds.name }))
      else toast.error(r.error ?? t('pg.dataPages.conn.connectionFailed'))
    } catch {
      setTestResults(p => ({ ...p, [ds.id]: false }))
      setTestErrors(p => ({ ...p, [ds.id]: t('pg.dataPages.conn.testFailed') }))
      toast.error(t('pg.dataPages.conn.testFailed'))
    }
    finally { setTesting(null) }
  }

  const shown = srcFilter.filtered.filter(ds => !typeFilter || ds.type === typeFilter)
  const types = [...new Set(sources.map(s => s.type))]
  const where = (ds: DataSource) => [ds.config.host ? String(ds.config.host) + (ds.config.database ? `/${ds.config.database}` : '') : '',
    !ds.config.host && ds.config.database ? String(ds.config.database) : '', ds.config.url ? String(ds.config.url).slice(0, 50) : '',
    !ds.config.host && !ds.config.url && ds.config.path ? String(ds.config.path).split('/').pop() : ''].filter(Boolean).join('')

  return (
    <div className="dl-cn">
      <header className="dl-cn__head">
        <div>
          <h1 className="dl-page-title">{t('nav.connections')}</h1>
          <p className="dl-page-head__sub">{t('cn2.sub')}</p>
        </div>
        {canAdminister && (
          <div className="dl-cn__head-acts">
            {sources.length > 0 && (
              <button className="btn btn-ghost" onClick={() => setCombining(true)}>{t('pg.dataPages.combine.open')}</button>
            )}
            <button className="btn btn-primary" onClick={() => setModal('add')} aria-label={t('connections.new')}>
              <Plus size={16} aria-hidden /> {t('cn2.new')}
            </button>
          </div>
        )}
      </header>
      {combining && <CombineDialog sources={sources} onClose={() => setCombining(false)} />}

      {!canAdminister && (
        /* Silently removing controls leaves someone hunting for a button that was
           in the screenshot a colleague sent them. One sentence prevents that. */
        <p className="dl-conn-notice">
          <Info size={16} aria-hidden style={{ flexShrink: 0, marginBlockStart: 1 }} />
          <span>{t('connections.viewerNote')}</span>
        </p>
      )}

      {sources.length > 0 && (
        <div className="dl-cn-tools">
          {srcFilter.input}
          {types.length > 1 && (
            <FilterChip icon={<Database size={15} aria-hidden />} label={typeFilter ? (TYPE_LABEL[typeFilter] ?? typeFilter) : t('cn2.type')}
              active={!!typeFilter} options={types.map(ty => ({ value: ty, label: TYPE_LABEL[ty] ?? ty, checked: typeFilter === ty }))}
              onPick={v => setTypeFilter(f => (f === v ? null : v))} />
          )}
          <span className="dl-cn-grow" />
          <span className="dl-cn-count">{localDigits(t('cn2.count', { n: shown.length }))}</span>
        </div>
      )}

      {loading && (
        <div className="dl-cn-table is-loading" aria-busy="true">
          <p className="dl-sr-only">{t('cn2.loading')}</p>
          {[0, 1, 2, 3].map(i => <div key={i} className="dl-cn-skel" aria-hidden><i /><i /><i /><i /></div>)}
        </div>
      )}

      {!loading && !!loadError && (
        <LoadError what="connections" title={t('pg.dataPages.conn.loadError')} error={loadError}
          onRetry={() => window.location.reload()} />
      )}

      {!loading && !loadError && sources.length === 0 && (
        <div className="dl-cn-empty">
          <span className="dl-cn-empty__art" aria-hidden><Database size={26} /><i /><Cable size={26} /></span>
          <h2>{t('cn2.emptyTitle')}</h2>
          <p>{t('cn2.emptyBody')}</p>
          <div className="dl-cn-empty__acts">
            {canAdminister && <button className="btn btn-primary" onClick={() => setModal('add')}><Plus size={16} aria-hidden /> {t('cn2.new')}</button>}
            <Link className="btn btn-ghost" to="/upload"><Upload size={16} aria-hidden /> {t('cn2.upload')}</Link>
          </div>
        </div>
      )}

      {srcFilter.noMatches && (
        <p className="dl-nomatch">{t('common.nothingMatches', { q: srcFilter.query })}</p>
      )}

      {!loading && shown.length > 0 && (
        <div className="dl-cn-table" role="table" aria-label={t('nav.connections')}>
          <div className="dl-cn-row dl-cn-row--h" role="row">
            <span role="columnheader">{t('cn2.h.conn')}</span>
            <span role="columnheader">{t('cn2.h.status')}</span>
            <span role="columnheader">{t('cn2.h.sync')}</span>
            <span role="columnheader" className="is-num">{t('cn2.h.datasets')}</span>
            <span role="columnheader"><span className="dl-sr-only">{t('cn2.h.actions')}</span></span>
          </div>
          {srcFilter.filtered.map(ds => {
            if (typeFilter && ds.type !== typeFilter) return null
            const testRes = testResults[ds.id]
            const run = syncs[ds.id]
            const status = testRes === true ? 'ok' : testRes === false ? 'fail'
              : run?.status === 'running' ? 'syncing' : run?.status === 'failed' ? 'syncFailed'
              : run?.status === 'ok' || run?.status === 'partial' ? 'synced' : 'untested'
            const tone = status === 'ok' || status === 'synced' ? 'ok' : status === 'fail' || status === 'syncFailed' ? 'err' : status === 'syncing' ? 'run' : 'none'
            const synced = run?.finished_at ? formatTimeAgo(run.finished_at, t) : null
            return (
              <div key={ds.id} className="dl-cn-row" role="row">
                <span role="cell" className="dl-cn-who">
                  <span className={`dl-cn-logo dl-cn-logo--${ds.type}`} aria-hidden>
                    {ds.config.url ? <Cable size={17} /> : <Database size={17} />}
                  </span>
                  <span className="dl-cn-who__tx">
                    <Link to={`/connections/${ds.id}/review`} className="dl-cn-name" dir="auto">{ds.name}</Link>
                    <span className="dl-cn-where">
                      {TYPE_LABEL[ds.type] ?? ds.type}{ds.custom_connector_label ? ` · ${ds.custom_connector_label}` : ''}
                      {where(ds) && <> · <code dir="ltr">{where(ds)}</code></>}
                    </span>
                  </span>
                </span>
                <span role="cell" className="dl-cn-st">
                  <span className={`dl-cn-pill dl-cn-pill--${tone}`}>
                    {tone === 'run' ? <Loader2 size={11} aria-hidden className="dl-cn-spin" /> : <span className="dl-cn-pill__dot" aria-hidden />}
                    {t(`cn2.st.${status}`)}
                  </span>
                  {testRes != null && (
                    testRes === false && testErrors[ds.id] ? (
                      <span className="dl-cn-st__err" role="status" data-testid="conn-test-error" title={testErrors[ds.id]}>
                        <span dir="auto">{testErrors[ds.id].split('\n')[0].replace(/\s*\(Background on this error.*$/, '').slice(0, 240)}</span>
                        {canAdminister && <button type="button" className="dl-cn-fix" onClick={() => setModal(ds)}>{t('cn2.fix')}</button>}
                      </span>
                    ) : <span className="dl-cn-st__sub">{t('cn2.checkedNow')}</span>
                  )}
                  {testRes == null && run?.status === 'failed' && run.error && (
                    <span className="dl-cn-st__err" title={run.error}><span dir="auto">{run.error.slice(0, 120)}</span></span>
                  )}
                </span>
                <span role="cell" className="dl-cn-muted">{synced ? localDigits(synced) : run ? t('cn2.never') : '—'}</span>
                <span role="cell" className="is-num" dir="ltr">{localDigits(String(datasetCount[ds.id] ?? 0))}</span>
                <span role="cell" className="dl-cn-acts">
                  {canAdminister && (
                    <span className="dl-cn-hover">
                      <button className="dl-cn-ib" onClick={() => handleTest(ds)} disabled={testing === ds.id}
                        aria-label={t('cn2.test', { name: ds.name })} title={testing === ds.id ? t('connections.testing') : t('connections.test')}>
                        {testing === ds.id ? <Loader2 size={15} aria-hidden className="dl-cn-spin" /> : <PlugZap size={15} aria-hidden />}
                        <span className="dl-sr-only">{t('connections.test')}</span>
                      </button>
                      <button className="dl-cn-ib" onClick={() => setBrowser(ds)} aria-label={t('cn2.browse', { name: ds.name })} title={t('connections.browse')}>
                        <Table2 size={15} aria-hidden /><span className="dl-sr-only">{t('connections.browse')}</span>
                      </button>
                      <button className="dl-cn-ib" onClick={() => setBuilding(ds)} aria-label={t('cn2.build', { name: ds.name })} title={t('connections.queryBuilderTitle')}>
                        <Code2 size={15} aria-hidden /><span className="dl-sr-only">{t('connections.queryBuilder')}</span>
                      </button>
                    </span>
                  )}
                  {/* Guided setup (the teammate's flow): on every row, for everyone who can see it. */}
                  <Link className="btn btn-ghost btn-sm dl-cn-setup" to={`/setup/${ds.id}`}>
                    <Compass size={14} aria-hidden />
                    {journeys[ds.id]
                      ? t('setup.continueStep', { n: localDigits(String(journeys[ds.id].position)), total: localDigits(String(journeys[ds.id].total)) })
                      : t('setup.start')}
                  </Link>
                  <Link className="btn btn-sm dl-cn-open" to={`/connections/${ds.id}/review`} aria-label={t('cn2.openNamed', { name: ds.name })}>{t('cn2.open')}</Link>
                  <ActionMenu
                    label={t('connections.more', { name: ds.name })}
                    align="end" portal
                    items={[
                      { key: 'metadata', label: t('connections.metadata'), icon: <ScanSearch size={16} />,
                        onSelect: () => goTo(`/connections/${ds.id}/review`) },
                      ...(canAdminister ? [
                        { key: 'edit', label: t('admin.edit'), icon: <Pencil size={16} />, onSelect: () => setModal(ds) },
                        { key: 'delete', label: t('admin.delete'), danger: true, icon: <Trash2 size={16} />, onSelect: () => void handleDelete(ds) },
                      ] : []),
                    ]}
                  />
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Imports run as server-side jobs; this is where one started from the
          browser can be found again after the dialog is closed. Admin-only,
          like the import itself. */}
      {canAdminister && <ImportQueue refreshKey={queueKey} />}

      {modal && catalog.length > 0 && (
        <ConnectionModal
          initial={modal === 'add' ? null : modal}
          catalog={catalog}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
      {browser && (
        <SchemaBrowser ds={browser} onClose={() => setBrowser(null)}
          onQueued={() => setQueueKey(k => k + 1)} />
      )}
      {building && (
        <QueryBuilderDialog ds={building} onClose={() => setBuilding(null)}
          onCreated={id => goTo(`/datasets/${id}`)} />
      )}
    </div>
  )
}
