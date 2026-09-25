import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dataSourcesApi } from '../../services/api'
import type { DataSource } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import IconLabel from '../../components/ui/IconLabel'
import { Cable, Clipboard, Database, Download, Eye } from 'lucide-react'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { TYPE_LABEL } from './typeMaps'

/* ── Schema Browser ────────────────────────────────────── */
export function SchemaBrowser({ ds, onClose }: { ds: DataSource; onClose: () => void }) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const navigate = useNavigate()
  const [tables,    setTables]    = useState<{ name: string; kind: string }[]>([])
  const [loading,   setLoading]   = useState(true)
  const [selected,  setSelected]  = useState<string | null>(null)
  const [query,     setQuery]     = useState('')
  const [preview,   setPreview]   = useState<{ columns: string[]; rows: unknown[][]; total: number } | null>(null)
  const [pvLoad,    setPvLoad]    = useState(false)
  const [importing, setImporting] = useState(false)
  const [dsName,    setDsName]    = useState('')
  const [mode,      setMode]      = useState<'import' | 'directquery'>('import')
  const [schemaError, setSchemaError] = useState<string | null>(null)
  const [attempt,   setAttempt]   = useState(0)

  // A failed schema read is shown IN the table list, where the reader is
  // looking, rather than as a toast over a panel that then said "No tables
  // found" -- which read as "connected, and the database is empty".
  useEffect(() => {
    setLoading(true)
    setSchemaError(null)
    dataSourcesApi.schema(ds.id)
      .then(r => setTables(r.tables))
      .catch(e => setSchemaError(e?.response?.data?.detail ?? 'Could not read the tables on this connection.'))
      .finally(() => setLoading(false))
  }, [ds.id, attempt])

  // A failed preview (bad SQL, missing table) stays IN the preview area with
  // the source's own message: a toast that vanished left the pane saying
  // "Select a table…" as if nothing had been tried.
  const [pvError, setPvError] = useState<{ msg: string; raw?: string } | null>(null)
  const loadPreview = async (table?: string, q?: string) => {
    setPvLoad(true)
    setPreview(null)
    setPvError(null)
    try {
      const r = await dataSourcesApi.preview(ds.id, table, q, 50)
      setPreview(r)
    } catch (e: any) {
      const d = e?.response?.data
      const raw: string | undefined = typeof d?.detail_raw === 'string' ? d.detail_raw : undefined
      const msg = typeof d?.detail === 'string' ? d.detail : 'Preview failed'
      // Postgres names the exact token; surface that line for a SQL error.
      const sqlLine = raw?.match(/syntax error[^\n]*/i)?.[0]
      setPvError({ msg: sqlLine ? `The source rejected the query: ${sqlLine}` : msg, raw })
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
      const r = await dataSourcesApi.import(ds.id, dsName, selected ?? undefined, query.trim() || undefined, mode)
      toast.success(mode === 'directquery' ? `"${r.name}" connected — queries the live source directly` : `Imported "${r.name}" — ${r.row_count.toLocaleString()} rows`)
      // Land on the new dataset, as Upload does -- not on Home.
      navigate(`/datasets/${r.id}`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Import failed')
    } finally { setImporting(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={`Browse ${ds.name}`}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        width: '85vw', maxWidth: 1100, height: '80vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px',
          borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <span aria-hidden style={{ inlineSize: 32, blockSize: 32, borderRadius: 8, flexShrink: 0,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'color-mix(in srgb, var(--accent) 12%, transparent)', color: 'var(--accent)' }}>
            <Database size={16} />
          </span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>{ds.name}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)' }}>
              {TYPE_LABEL[ds.type]}{ds.custom_connector_label ? ` · ${ds.custom_connector_label}` : ''}
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
          {/* Left: table list */}
          {ds.type !== 'api' && (
            <div style={{ width: 220, borderInlineEnd: '1px solid var(--border)', overflowY: 'auto',
              padding: '12px 8px', flexShrink: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
                letterSpacing: '.06em', padding: '0 6px', marginBottom: 8 }}>Tables & Views</div>
              {loading && <p style={{ fontSize: 11, color: 'var(--muted)', padding: '0 6px' }}>Loading…</p>}
              {!loading && schemaError && (
                <div role="alert" style={{ margin: '0 4px', padding: '10px 10px', borderRadius: 8, fontSize: 12,
                  background: 'var(--dl-error-bg)', border: '1px solid var(--dl-error-line)', color: 'var(--text)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--dl-error-text)', marginBottom: 4 }}>Could not connect</div>
                  <div style={{ marginBottom: 8 }}>{schemaError}</div>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAttempt(a => a + 1)}>Try again</button>
                </div>
              )}
              {!loading && !schemaError && tables.length === 0 && <p style={{ fontSize: 11, color: 'var(--muted)', padding: '0 6px' }}>No tables found</p>}
              {tables.map(t => (
                <button key={t.name} onClick={() => handleSelect(t.name)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '5px 8px',
                    background: selected === t.name ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent',
                    border: 'none', borderRadius: 5, cursor: 'pointer', textAlign: 'start',
                    color: selected === t.name ? 'var(--accent)' : 'var(--text)', fontSize: 12 }}>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>{t.kind === 'view' ? <Eye size={11} /> : <Clipboard size={11} />}</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
                </button>
              ))}
            </div>
          )}

          {/* Right: SQL + preview */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, padding: 16 }}>
            {/* Custom query */}
            <div style={{ marginBottom: 10, flexShrink: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
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
              {!pvLoad && !preview && pvError && (
                <div role="alert" className="dl-conn-test dl-conn-test--fail" style={{ margin: 12 }}>
                  <span style={{ minWidth: 0 }}>
                    {pvError.msg}
                    {pvError.raw && (
                      <details className="dl-conn-test__raw"><summary>Technical details</summary><pre>{pvError.raw}</pre></details>
                    )}
                  </span>
                </div>
              )}
              {!pvLoad && !preview && !pvError && (
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
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)', flexShrink: 0 }}>
                    {preview.total} rows preview
                  </div>
                  <div style={{ display: 'flex', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden', flexShrink: 0 }}>
                    {(['import', 'directquery'] as const).map(m => (
                      <button key={m} onClick={() => setMode(m)}
                        style={{ padding: '5px 10px', fontSize: 11, border: 'none', cursor: 'pointer',
                          background: mode === m ? 'var(--accent)' : 'var(--surface2)',
                          color: mode === m ? 'var(--mc-accent-fg)' : 'var(--text)' }}>
                        {m === 'import' ? 'Import' : 'DirectQuery'}
                      </button>
                    ))}
                  </div>
                  <input value={dsName} onChange={e => setDsName(e.target.value)}
                    placeholder="Dataset name…"
                    style={{ flex: 1, fontSize: 12, padding: '5px 8px', background: 'var(--surface2)',
                      border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }} />
                  <button className="btn btn-primary btn-sm" onClick={handleImport} disabled={importing}>
                    {importing
                      ? (mode === 'directquery' ? 'Connecting…' : 'Importing…')
                      : (mode === 'directquery'
                  ? <IconLabel icon={Cable}>Create DirectQuery Dataset</IconLabel>
                  : <IconLabel icon={Download}>Import as Dataset</IconLabel>)}
                  </button>
                </div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {mode === 'directquery'
                    ? 'Queries the live source on every widget render — no data copied to this server.'
                    : 'Copies the current result set into this app; refresh by re-importing.'}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

