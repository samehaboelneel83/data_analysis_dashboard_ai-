import { useEffect, useState } from 'react'
import LoadError from '../components/ui/LoadError'
import { useNavigate } from 'react-router-dom'
import { useOptionalAuth } from '../contexts/AuthContext'
import { dataSourcesApi } from '../services/api'
import type { DataSource, ConnectorSpec } from '../services/api'
import toast from 'react-hot-toast'
import { useConfirm } from '../components/ui/ConfirmDialog'
import QueryBuilderDialog from '../components/QueryBuilderDialog'
import { useListFilter } from '../components/ui/ListFilter'
import IconLabel from '../components/ui/IconLabel'
import {
  Check, X as XIcon, Cable, Database, Info, Pencil,
  Plus, ScanSearch, TriangleAlert, Trash2,
} from 'lucide-react'
import ActionMenu from '../components/ActionMenu'
import { useT } from '../i18n'

import { TYPE_ICON, TYPE_LABEL } from './connections/typeMaps'
import { ConnectionModal } from './connections/ConnectionModal'
import { SchemaBrowser } from './connections/SchemaBrowser'
export { SchemaBrowser } from './connections/SchemaBrowser'

/* ── Main Connections Page ─────────────────────────────── */
export default function Connections() {
  const t = useT()
  const [sources,  setSources]  = useState<DataSource[]>([])
  const srcFilter = useListFilter(sources,
    d => [d.name, d.type], 'Search connections')
  const [catalog,  setCatalog]  = useState<ConnectorSpec[]>([])
  const [loading,  setLoading]  = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal,    setModal]    = useState<'add' | DataSource | null>(null)
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
  const [testing,  setTesting]  = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, boolean | null>>({})

  useEffect(() => {
    // Without the catch, a server error cleared `loading` and fell through to
    // "No connections yet" -- a claim about the user's estate rather than about
    // our ability to read it.
    setLoadError(null)
    dataSourcesApi.list().then(setSources)
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
    // Fetch the connector catalog and populate the icon/label maps in place so
    // list rows and the schema browser render a friendly name for any type.
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
    if (isNew && ds.sync_run_id) goTo(`/connections/${ds.id}/review`)
  }

  const confirm = useConfirm()
  const handleDelete = async (ds: DataSource) => {
    if (!await confirm({ title: `Delete "${ds.name}"?`, body: 'This cannot be undone.' })) return
    await dataSourcesApi.delete(ds.id)
    setSources(prev => prev.filter(s => s.id !== ds.id))
    toast.success('Deleted')
  }

  const handleTest = async (ds: DataSource) => {
    setTesting(ds.id)
    setTestResults(p => ({ ...p, [ds.id]: null }))
    try {
      const r = await dataSourcesApi.test(ds.id)
      setTestResults(p => ({ ...p, [ds.id]: r.ok }))
      if (r.ok) toast.success(`${ds.name} — connected`)
      else toast.error(r.error ?? 'Connection failed')
    } catch { toast.error('Test failed') }
    finally { setTesting(null) }
  }

  return (
    <div>
      <header className="dl-page-head">
        <div>
          <h1 className="dl-page-head__title">{t('nav.connections')}</h1>
          <p className="dl-page-head__sub">
            Live databases and APIs your datasets and dashboards read from.
          </p>
        </div>
        {canAdminister && (
          <button className="btn btn-primary" onClick={() => setModal('add')}>
            <Plus size={16} /> {t('connections.new')}
          </button>
        )}
      </header>

      {/* The search box sits with the list it filters, not in the page header
          beside an action that CREATES connections rather than finds them. */}
      {srcFilter.input && <div className="dl-toolbar">{srcFilter.input}</div>}

      {loading && <p className="dl-muted-line">Loading…</p>}

      {!loading && !!loadError && (
        <LoadError what="connections" error={loadError}
          onRetry={() => window.location.reload()} />
      )}

      {!loading && !loadError && sources.length === 0 && (
        <div className="card dl-empty">
          <Cable size={40} className="dl-empty__icon" aria-hidden />
          <p className="dl-empty__title">No connections yet</p>
          <p className="dl-empty__body">
            Connect to PostgreSQL, SQL Server, MySQL, Oracle, SQLite or a Web API
          </p>
        </div>
      )}

      {!canAdminister && (
        /* Silently removing controls leaves someone hunting for a button that was
           in the screenshot a colleague sent them. One sentence prevents that. */
        <p className="dl-conn-notice">
          <Info size={16} aria-hidden style={{ flexShrink: 0, marginBlockStart: 1 }} />
          <span>
            You can see the connections your dashboards use. Adding, editing, testing
            and browsing them is done by an organisation administrator.
          </span>
        </p>
      )}
      {srcFilter.noMatches && (
        <p className="dl-nomatch">Nothing matches “{srcFilter.query}”.</p>
      )}
      <div className={sources.length > 0 && !srcFilter.noMatches ? 'card dl-conn-list' : undefined}>
        {srcFilter.filtered.map(ds => {
          const testRes = testResults[ds.id]
          return (
            <div key={ds.id} className="dl-conn">
              <span className="dl-conn__icon" aria-hidden>
                {ds.config.url ? <Cable size={18} /> : <Database size={18} />}
              </span>
              <div className="dl-conn__body">
                <div className="dl-conn__name">{ds.name}</div>
                <div className="dl-conn__meta">
                  {TYPE_LABEL[ds.type]}
                  {ds.custom_connector_label ? ` · ${ds.custom_connector_label}` : ''}
                  {ds.config.host ? ` · ${ds.config.host}` : ''}
                  {ds.config.database ? `/${ds.config.database}` : ''}
                  {ds.config.url ? ` · ${String(ds.config.url).slice(0, 50)}` : ''}
                </div>
              </div>

              {testRes === true && (
                <span className="dl-conn__status dl-conn__status--ok">
                  <IconLabel icon={Check} size={12}>Connected</IconLabel>
                </span>
              )}
              {testRes === false && (
                <span className="dl-conn__status dl-conn__status--fail">
                  <IconLabel icon={XIcon} size={12}>Failed</IconLabel>
                </span>
              )}

              {/* Administering a connection -- testing its credentials, importing
                  from it, editing or deleting it -- is refused by the API for
                  anyone who is not an admin or the person who added it. Offering
                  the buttons anyway produced a row of controls that exist in
                  order to be refused, which is worse than no controls: the person
                  cannot tell whether they did something wrong, the product is
                  broken, or they were never allowed. */}
              {/* Administering a connection is refused by the API for anyone
                  who is not an admin or the person who added it, so the
                  controls are absent rather than present-and-refused.

                  THREE visible, the rest in one menu. Six equal ghost buttons
                  per row made every connection shout six times and put Delete
                  the same distance from the cursor as Test; the three kept are
                  the ones you reach for while USING a source, and the menu
                  spells out the rest instead of making them compete. */}
              {canAdminister && (
                <div className="dl-conn__actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => handleTest(ds)}
                    disabled={testing === ds.id}>
                    {testing === ds.id ? 'Testing…' : 'Test'}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setBrowser(ds)}>
                    Browse
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setBuilding(ds)}
                    title="Build a query visually: tables, joins, aggregations">
                    Query builder
                  </button>
                  <ActionMenu
                    label={`More actions for ${ds.name}`}
                    align="end"
                    items={[
                      { key: 'metadata', label: 'Metadata',
                        icon: <ScanSearch size={16} />,
                        onSelect: () => goTo(`/connections/${ds.id}/review`) },
                      { key: 'edit', label: 'Edit', icon: <Pencil size={16} />,
                        onSelect: () => setModal(ds) },
                      { key: 'delete', label: 'Delete', danger: true,
                        icon: <Trash2 size={16} />,
                        onSelect: () => void handleDelete(ds) },
                    ]}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {modal && catalog.length > 0 && (
        <ConnectionModal
          initial={modal === 'add' ? null : modal}
          catalog={catalog}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
      {browser && (
        <SchemaBrowser ds={browser} onClose={() => setBrowser(null)} />
      )}
      {building && (
        <QueryBuilderDialog ds={building} onClose={() => setBuilding(null)} />
      )}
    </div>
  )
}
