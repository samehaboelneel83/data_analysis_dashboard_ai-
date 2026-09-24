import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dataSourcesApi } from '../services/api'
import type { DataSource } from '../services/api'
import toast from 'react-hot-toast'

/* ── Icons per type ────────────────────────────────────── */
const TYPE_ICON: Record<string, string> = {
  postgresql: '🐘', sqlserver: '🪟', mysql: '🐬',
  oracle: '🔴', sqlite: '📁', api: '🌐',
}
const TYPE_LABEL: Record<string, string> = {
  postgresql: 'PostgreSQL', sqlserver: 'SQL Server', mysql: 'MySQL',
  oracle: 'Oracle', sqlite: 'SQLite', api: 'Web API',
}

/* ── Default blank configs per type ───────────────────── */
const BLANK_CONFIG: Record<string, Record<string, unknown>> = {
  postgresql: { host: '', port: 5432,  database: '', username: '', password: '', schema: '' },
  sqlserver:  { host: '', port: 1433,  database: '', username: '', password: '' },
  mysql:      { host: '', port: 3306,  database: '', username: '', password: '' },
  oracle:     { host: '', port: 1521,  service_name: '', username: '', password: '' },
  sqlite:     { filepath: '' },
  api:        { url: '', method: 'GET', auth_type: 'none', token: '', api_key: '',
                key_header: 'X-API-Key', username: '', password: '',
                headers: {}, params: {}, json_path: '', body: {} },
}

/* ── Connection Form Modal ─────────────────────────────── */
function ConnectionModal({ initial, onSave, onClose }: {
  initial?: DataSource | null
  onSave: (ds: DataSource) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [name,    setName]    = useState(initial?.name ?? '')
  const [type,    setType]    = useState(initial?.type ?? 'postgresql')
  const [cfg,     setCfg]     = useState<Record<string, unknown>>(
    initial?.config ?? BLANK_CONFIG['postgresql']
  )
  const [testing, setTesting] = useState(false)
  const [testOk,  setTestOk]  = useState<boolean | null>(null)
  const [saving,  setSaving]  = useState(false)

  const setField = (k: string, v: unknown) => setCfg(p => ({ ...p, [k]: v }))

  const changeType = (t: string) => {
    setType(t)
    setCfg(BLANK_CONFIG[t] ?? {})
    setTestOk(null)
  }

  const handleTest = async () => {
    if (!initial?.id) { toast.error('Save first, then test'); return }
    setTesting(true)
    setTestOk(null)
    try {
      const r = await dataSourcesApi.test(initial.id)
      setTestOk(r.ok)
      if (r.ok) toast.success('Connection successful')
      else toast.error(r.error ?? 'Connection failed')
    } catch { toast.error('Test failed') }
    finally { setTesting(false) }
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await dataSourcesApi.update(initial!.id, { name, type, config: cfg })
        : await dataSourcesApi.create({ name, type, config: cfg })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Connection created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 480, maxHeight: '90vh', overflowY: 'auto' }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Connection' : 'New Connection'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        {/* Name */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Connection Name *</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="My Database" {...inp} />
        </label>

        {/* Type */}
        <label style={{ display: 'block', marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Type</div>
          <select value={type} onChange={e => changeType(e.target.value)} {...inp}>
            {Object.keys(TYPE_LABEL).map(t => (
              <option key={t} value={t}>{TYPE_ICON[t]} {TYPE_LABEL[t]}</option>
            ))}
          </select>
        </label>

        {/* Type-specific fields */}
        {['postgresql', 'sqlserver', 'mysql'].includes(type) && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 8, marginBottom: 8 }}>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Host</div>
              <input value={cfg.host as string ?? ''} onChange={e => setField('host', e.target.value)} placeholder="localhost" {...inp} />
            </label>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Port</div>
              <input type="number" value={cfg.port as number ?? ''} onChange={e => setField('port', +e.target.value)} {...inp} />
            </label>
          </div>
        )}
        {type === 'oracle' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 8, marginBottom: 8 }}>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Host</div>
              <input value={cfg.host as string ?? ''} onChange={e => setField('host', e.target.value)} placeholder="oracle-host" {...inp} />
            </label>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Port</div>
              <input type="number" value={cfg.port as number ?? ''} onChange={e => setField('port', +e.target.value)} {...inp} />
            </label>
          </div>
        )}
        {['postgresql', 'sqlserver', 'mysql'].includes(type) && (
          <label style={{ display: 'block', marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Database</div>
            <input value={cfg.database as string ?? ''} onChange={e => setField('database', e.target.value)} placeholder="my_database" {...inp} />
          </label>
        )}
        {type === 'oracle' && (
          <label style={{ display: 'block', marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Service Name</div>
            <input value={cfg.service_name as string ?? ''} onChange={e => setField('service_name', e.target.value)} placeholder="ORCL" {...inp} />
          </label>
        )}
        {type === 'postgresql' && (
          <label style={{ display: 'block', marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Schema (optional)</div>
            <input value={cfg.schema as string ?? ''} onChange={e => setField('schema', e.target.value)} placeholder="public" {...inp} />
          </label>
        )}
        {['postgresql', 'sqlserver', 'mysql', 'oracle'].includes(type) && (<>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Username</div>
              <input value={cfg.username as string ?? ''} onChange={e => setField('username', e.target.value)} autoComplete="off" {...inp} />
            </label>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Password</div>
              <input type="password" value={cfg.password as string ?? ''} onChange={e => setField('password', e.target.value)} autoComplete="off" {...inp} />
            </label>
          </div>
        </>)}
        {type === 'sqlite' && (
          <label style={{ display: 'block', marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>File Path</div>
            <input value={cfg.filepath as string ?? ''} onChange={e => setField('filepath', e.target.value)} placeholder="/data/mydb.db" {...inp} />
          </label>
        )}

        {/* Web API fields */}
        {type === 'api' && (<>
          <label style={{ display: 'block', marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>URL *</div>
            <input value={cfg.url as string ?? ''} onChange={e => setField('url', e.target.value)} placeholder="https://api.example.com/data" {...inp} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Method</div>
              <select value={cfg.method as string ?? 'GET'} onChange={e => setField('method', e.target.value)} {...inp}>
                <option>GET</option><option>POST</option>
              </select>
            </label>
            <label>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Auth</div>
              <select value={cfg.auth_type as string ?? 'none'} onChange={e => setField('auth_type', e.target.value)} {...inp}>
                <option value="none">None</option>
                <option value="bearer">Bearer Token</option>
                <option value="api_key">API Key</option>
                <option value="basic">Basic Auth</option>
              </select>
            </label>
          </div>
          {cfg.auth_type === 'bearer' && (
            <label style={{ display: 'block', marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Token</div>
              <input value={cfg.token as string ?? ''} onChange={e => setField('token', e.target.value)} {...inp} />
            </label>
          )}
          {cfg.auth_type === 'api_key' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <label>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Header Name</div>
                <input value={cfg.key_header as string ?? 'X-API-Key'} onChange={e => setField('key_header', e.target.value)} {...inp} />
              </label>
              <label>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Key Value</div>
                <input value={cfg.api_key as string ?? ''} onChange={e => setField('api_key', e.target.value)} {...inp} />
              </label>
            </div>
          )}
          {cfg.auth_type === 'basic' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <label>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Username</div>
                <input value={cfg.username as string ?? ''} onChange={e => setField('username', e.target.value)} {...inp} />
              </label>
              <label>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>Password</div>
                <input type="password" value={cfg.password as string ?? ''} onChange={e => setField('password', e.target.value)} {...inp} />
              </label>
            </div>
          )}
          <label style={{ display: 'block', marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>JSON Path (e.g. data.records)</div>
            <input value={cfg.json_path as string ?? ''} onChange={e => setField('json_path', e.target.value)} placeholder="data.items" {...inp} />
          </label>
        </>)}

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          {isEdit && (
            <button className="btn btn-ghost" onClick={handleTest} disabled={testing}
              style={{ fontSize: 12, padding: '6px 14px' }}>
              {testing ? 'Testing…' : testOk === true ? '✅ Test' : testOk === false ? '❌ Test' : 'Test'}
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

/* ── Schema Browser ────────────────────────────────────── */
function SchemaBrowser({ ds, onClose }: { ds: DataSource; onClose: () => void }) {
  const navigate = useNavigate()
  const [tables,    setTables]    = useState<{ name: string; kind: string }[]>([])
  const [loading,   setLoading]   = useState(true)
  const [selected,  setSelected]  = useState<string | null>(null)
  const [query,     setQuery]     = useState('')
  const [preview,   setPreview]   = useState<{ columns: string[]; rows: unknown[][]; total: number } | null>(null)
  const [pvLoad,    setPvLoad]    = useState(false)
  const [importing, setImporting] = useState(false)
  const [dsName,    setDsName]    = useState('')

  useEffect(() => {
    setLoading(true)
    dataSourcesApi.schema(ds.id)
      .then(r => setTables(r.tables))
      .catch(e => toast.error(e?.response?.data?.detail ?? 'Failed to load schema'))
      .finally(() => setLoading(false))
  }, [ds.id])

  const loadPreview = async (table?: string, q?: string) => {
    setPvLoad(true)
    setPreview(null)
    try {
      const r = await dataSourcesApi.preview(ds.id, table, q, 50)
      setPreview(r)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Preview failed')
    } finally { setPvLoad(false) }
  }

  const handleSelect = (t: string) => {
    setSelected(t)
    setQuery('')
    setDsName(t)
    loadPreview(t)
  }

  const handleRunQuery = () => {
    if (!query.trim()) return
    setSelected(null)
    setDsName('query_result')
    loadPreview(undefined, query)
  }

  const handleImport = async () => {
    if (!dsName.trim()) { toast.error('Enter a dataset name'); return }
    setImporting(true)
    try {
      const r = await dataSourcesApi.import(ds.id, dsName, selected ?? undefined, query.trim() || undefined)
      toast.success(`Imported "${r.name}" — ${r.row_count.toLocaleString()} rows`)
      navigate('/')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Import failed')
    } finally { setImporting(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        width: '85vw', maxWidth: 1100, height: '80vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px',
          borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <span style={{ fontSize: 18 }}>{TYPE_ICON[ds.type]}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>{ds.name}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)' }}>{TYPE_LABEL[ds.type]}</div>
          </div>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
          {/* Left: table list */}
          {ds.type !== 'api' && (
            <div style={{ width: 220, borderRight: '1px solid var(--border)', overflowY: 'auto',
              padding: '12px 8px', flexShrink: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
                letterSpacing: '.06em', padding: '0 6px', marginBottom: 8 }}>Tables & Views</div>
              {loading && <p style={{ fontSize: 11, color: 'var(--muted)', padding: '0 6px' }}>Loading…</p>}
              {!loading && tables.length === 0 && <p style={{ fontSize: 11, color: 'var(--muted)', padding: '0 6px' }}>No tables found</p>}
              {tables.map(t => (
                <button key={t.name} onClick={() => handleSelect(t.name)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '5px 8px',
                    background: selected === t.name ? 'rgba(108,143,255,.12)' : 'transparent',
                    border: 'none', borderRadius: 5, cursor: 'pointer', textAlign: 'left',
                    color: selected === t.name ? 'var(--accent)' : 'var(--text)', fontSize: 12 }}>
                  <span style={{ fontSize: 10, color: 'var(--muted)' }}>{t.kind === 'view' ? '👁' : '📋'}</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
                </button>
              ))}
            </div>
          )}

          {/* Right: SQL + preview */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, padding: 16 }}>
            {/* Custom query */}
            <div style={{ marginBottom: 10, flexShrink: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
                letterSpacing: '.06em', marginBottom: 6 }}>Custom Query</div>
              <textarea
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder={ds.type === 'api' ? 'Leave empty to fetch from URL directly' : 'SELECT * FROM table WHERE …'}
                rows={3}
                style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: 12, padding: '6px 8px',
                  background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
                  color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box' }}
              />
              <button className="btn btn-ghost btn-sm" onClick={handleRunQuery} disabled={pvLoad}
                style={{ marginTop: 4, fontSize: 11 }}>
                ▶ Run Preview
              </button>
            </div>

            {/* Preview table */}
            <div style={{ flex: 1, overflow: 'auto', background: 'var(--surface2)',
              border: '1px solid var(--border)', borderRadius: 8, marginBottom: 10 }}>
              {pvLoad && <div style={{ padding: 20, color: 'var(--muted)', fontSize: 12 }}>Loading preview…</div>}
              {!pvLoad && !preview && (
                <div style={{ padding: 20, color: 'var(--muted)', fontSize: 12 }}>
                  Select a table or run a query to preview data
                </div>
              )}
              {!pvLoad && preview && (
                <table style={{ fontSize: 11 }}>
                  <thead>
                    <tr>{preview.columns.map(c => <th key={c} style={{ whiteSpace: 'nowrap' }}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i}>
                        {(row as unknown[]).map((v, j) => (
                          <td key={j}>{v == null ? <span style={{ color: 'var(--muted)' }}>—</span> : String(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Import bar */}
            {preview && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', flexShrink: 0 }}>
                  {preview.total} rows preview
                </div>
                <input value={dsName} onChange={e => setDsName(e.target.value)}
                  placeholder="Dataset name…"
                  style={{ flex: 1, fontSize: 12, padding: '5px 8px', background: 'var(--surface2)',
                    border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }} />
                <button className="btn btn-primary btn-sm" onClick={handleImport} disabled={importing}>
                  {importing ? 'Importing…' : '📥 Import as Dataset'}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Main Connections Page ─────────────────────────────── */
export default function Connections() {
  const [sources,  setSources]  = useState<DataSource[]>([])
  const [loading,  setLoading]  = useState(true)
  const [modal,    setModal]    = useState<'add' | DataSource | null>(null)
  const [browser,  setBrowser]  = useState<DataSource | null>(null)
  const [testing,  setTesting]  = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, boolean | null>>({})

  useEffect(() => {
    dataSourcesApi.list().then(setSources).finally(() => setLoading(false))
  }, [])

  const handleSaved = (ds: DataSource) => {
    setSources(prev => {
      const idx = prev.findIndex(s => s.id === ds.id)
      return idx >= 0 ? prev.map(s => s.id === ds.id ? ds : s) : [ds, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (ds: DataSource) => {
    if (!confirm(`Delete "${ds.name}"?`)) return
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
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Connections</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')}>
          + New Connection
        </button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && sources.length === 0 && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔌</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>No connections yet</div>
          <div style={{ fontSize: 12 }}>Connect to PostgreSQL, SQL Server, MySQL, Oracle, SQLite or a Web API</div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {sources.map(ds => {
          const testRes = testResults[ds.id]
          return (
            <div key={ds.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 10, padding: '14px 16px' }}>
              <span style={{ fontSize: 26 }}>{TYPE_ICON[ds.type] ?? '🔌'}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{ds.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {TYPE_LABEL[ds.type]}
                  {ds.config.host ? ` · ${ds.config.host}` : ''}
                  {ds.config.database ? `/${ds.config.database}` : ''}
                  {ds.config.url ? ` · ${String(ds.config.url).slice(0, 50)}` : ''}
                </div>
              </div>

              {testRes === true  && <span style={{ fontSize: 12, color: '#34d399' }}>✅ Connected</span>}
              {testRes === false && <span style={{ fontSize: 12, color: '#f87171' }}>❌ Failed</span>}

              <button className="btn btn-ghost btn-sm" onClick={() => handleTest(ds)} disabled={testing === ds.id}
                style={{ fontSize: 11 }}>
                {testing === ds.id ? 'Testing…' : 'Test'}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setBrowser(ds)}
                style={{ fontSize: 11 }}>
                Browse
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setModal(ds)}
                style={{ fontSize: 11 }}>
                Edit
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(ds)}
                style={{ fontSize: 11, color: 'var(--danger)' }}>
                Delete
              </button>
            </div>
          )
        })}
      </div>

      {modal && (
        <ConnectionModal
          initial={modal === 'add' ? null : modal}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
      {browser && (
        <SchemaBrowser ds={browser} onClose={() => setBrowser(null)} />
      )}
    </div>
  )
}
