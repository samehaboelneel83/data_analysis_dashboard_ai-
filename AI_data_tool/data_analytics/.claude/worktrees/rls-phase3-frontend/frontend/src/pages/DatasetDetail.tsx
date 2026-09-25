import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { datasetsApi, analysisApi, dataPreviewApi, filterExprApi } from '../services/api'
import type { Dataset, CalcColumn, DataPreviewFilter } from '../services/api'
import CalcColumnsPanel from '../components/report/CalcColumnsPanel'
import toast from 'react-hot-toast'

type Tab = 'overview' | 'data'

const OPS: { value: DataPreviewFilter['op']; label: string }[] = [
  { value: 'eq',         label: '=='         },
  { value: 'ne',         label: '!='         },
  { value: 'gt',         label: '>'          },
  { value: 'lt',         label: '<'          },
  { value: 'gte',        label: '>='         },
  { value: 'lte',        label: '<='         },
  { value: 'contains',   label: 'contains'   },
  { value: 'startswith', label: 'starts with'},
]

const PAGE_SIZE = 100

export default function DatasetDetail() {
  const { id } = useParams<{ id: string }>()
  const dsId   = Number(id)

  const [ds,       setDs]       = useState<Dataset | null>(null)
  const [analysis, setAnalysis] = useState<any>(null)
  const [loading,  setLoading]  = useState(true)
  const [running,  setRunning]  = useState(false)
  const [tab,      setTab]      = useState<Tab>('overview')

  // Data tab state
  const [calcCols,   setCalcCols]   = useState<CalcColumn[]>([])
  const [filterRows, setFilterRows] = useState<{ id: number; column: string; op: DataPreviewFilter['op']; value: string }[]>([])
  const [nextFid,    setNextFid]    = useState(1)
  const [preview,    setPreview]    = useState<{ columns: string[]; rows: unknown[][]; total: number } | null>(null)
  const [pvError,    setPvError]    = useState<string | null>(null)
  const [pvLoading,  setPvLoading]  = useState(false)
  const [page,       setPage]       = useState(0)
  const [sortBy,     setSortBy]     = useState<string | null>(null)
  const [sortDir,    setSortDir]    = useState<'asc' | 'desc'>('asc')
  const [search,     setSearch]     = useState('')
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Global filter state
  const [filterExpr,    setFilterExpr]    = useState('')
  const [savedFilter,   setSavedFilter]   = useState<string | null>(null)
  const [filterPreview, setFilterPreview] = useState<{ ok: boolean; passing?: number; total: number; error?: string } | null>(null)
  const [filterSaving,  setFilterSaving]  = useState(false)
  const [refreshing,    setRefreshing]    = useState(false)

  useEffect(() => {
    datasetsApi.get(dsId).then(ds => {
      setDs(ds)
      setCalcCols(ds.calculated_columns ?? [])
      const expr = ds.default_filter_expr ?? ''
      setFilterExpr(expr)
      setSavedFilter(expr || null)
    })
    analysisApi.get(dsId).then(setAnalysis).catch(() => null).finally(() => setLoading(false))
  }, [dsId])

  const loadPreview = useCallback(async (
    pg    = page,
    frows = filterRows,
    cc    = calcCols,
    sb    = sortBy,
    sd    = sortDir,
    srch  = search,
  ) => {
    if (!ds) return
    setPvLoading(true)
    setPvError(null)
    try {
      const activeFilters: DataPreviewFilter[] = frows
        .filter(f => f.column && f.value !== '')
        .map(f => ({ column: f.column, op: f.op, value: f.value }))
      const result = await dataPreviewApi.query(
        dsId, activeFilters, cc, PAGE_SIZE, pg * PAGE_SIZE,
        sb ?? undefined, sd, srch || undefined,
      )
      setPreview(result)
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to load data'
      setPvError(msg)
    } finally {
      setPvLoading(false)
    }
  }, [ds, dsId, page, filterRows, calcCols, sortBy, sortDir, search])

  // Load preview whenever tab is 'data' and ds is ready
  useEffect(() => {
    if (tab === 'data' && ds) loadPreview(0, filterRows, calcCols)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, ds])

  const runAnalysis = async () => {
    setRunning(true)
    try {
      const r = await analysisApi.run(dsId)
      setAnalysis(r)
      toast.success('Analysis complete')
    } catch { toast.error('Analysis failed') }
    finally { setRunning(false) }
  }

  const applyFilters = () => {
    setPage(0)
    loadPreview(0, filterRows, calcCols, sortBy, sortDir, search)
  }

  const handleSort = (col: string) => {
    let newBy: string | null = col
    let newDir: 'asc' | 'desc' = 'asc'
    if (sortBy === col) {
      if (sortDir === 'asc') { newDir = 'desc' }
      else { newBy = null; newDir = 'asc' }
    }
    setSortBy(newBy)
    setSortDir(newDir)
    setPage(0)
    loadPreview(0, filterRows, calcCols, newBy, newDir, search)
  }

  const handleSearch = (val: string) => {
    setSearch(val)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setPage(0)
      loadPreview(0, filterRows, calcCols, sortBy, sortDir, val)
    }, 350)
  }

  const addFilter = () => {
    const firstCol = ds?.columns?.[0]?.name ?? ''
    setFilterRows(p => [...p, { id: nextFid, column: firstCol, op: 'eq', value: '' }])
    setNextFid(p => p + 1)
  }

  const updateFilter = (id: number, key: string, val: string) =>
    setFilterRows(p => p.map(f => f.id === id ? { ...f, [key]: val } : f))

  const removeFilter = (id: number) =>
    setFilterRows(p => p.filter(f => f.id !== id))

  const handleCalcColsChanged = (cols: CalcColumn[]) => {
    setCalcCols(cols)
    setPage(0)
    loadPreview(0, filterRows, cols, sortBy, sortDir, search)
  }

  const testGlobalFilter = async () => {
    if (!filterExpr.trim()) return
    setFilterPreview(null)
    try {
      const result = await filterExprApi.preview(dsId, filterExpr, calcCols)
      setFilterPreview(result)
    } catch {
      setFilterPreview({ ok: false, error: 'Request failed', total: 0 })
    }
  }

  const saveGlobalFilter = async (expr?: string) => {
    const val = expr !== undefined ? expr : filterExpr
    setFilterSaving(true)
    try {
      const updated = await filterExprApi.update(dsId, val || null)
      setDs(updated)
      setSavedFilter(val || null)
      setFilterPreview(null)
      toast.success(val ? 'Global filter saved' : 'Global filter cleared')
      if (tab === 'data') loadPreview(0, filterRows, calcCols, sortBy, sortDir, search)
    } catch {
      toast.error('Failed to save filter')
    } finally {
      setFilterSaving(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    setPvError(null)
    try {
      const updated = await datasetsApi.refresh(dsId)
      setDs(updated)
      setCalcCols(updated.calculated_columns ?? [])
      toast.success(`Refreshed — ${updated.row_count.toLocaleString()} rows loaded`)
      loadPreview(0, filterRows, updated.calculated_columns ?? [], sortBy, sortDir, search)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  const allColNames = [
    ...(ds?.columns ?? []).map(c => c.name),
    ...calcCols.map(c => c.name),
  ]

  const calcColNames = new Set(calcCols.map(c => c.name))

  if (!ds) return <p style={{ color: 'var(--muted)' }}>Loading…</p>

  const numCols = Object.entries(analysis?.numeric?.columns  ?? {})
  const catCols = Object.entries(analysis?.categorical?.columns ?? {})

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexShrink: 0 }}>
        <Link to="/" style={{ color: 'var(--muted)', fontSize: 12, textDecoration: 'none' }}>← Datasets</Link>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>{ds.name}</h1>
        {ds.data_source_id && (
          <button onClick={handleRefresh} disabled={refreshing} className="btn btn-ghost btn-sm">
            {refreshing ? 'Refreshing…' : '↻ Refresh from source'}
          </button>
        )}
        {tab === 'overview' && (
          <button onClick={runAnalysis} disabled={running} className="btn btn-primary btn-sm">
            {running ? 'Running…' : analysis ? 'Re-run analysis' : 'Run analysis'}
          </button>
        )}
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)', marginBottom: 20, flexShrink: 0 }}>
        {(['overview', 'data'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '8px 18px', border: 'none', background: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: tab === t ? 700 : 400,
              color: tab === t ? 'var(--accent)' : 'var(--muted)',
              borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1, fontFamily: 'var(--sans)', textTransform: 'capitalize' }}>
            {t === 'overview' ? '📊 Overview' : '🗂 Data'}
          </button>
        ))}
      </div>

      {/* ── Overview tab ── */}
      {tab === 'overview' && (
        <div>
          {analysis && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
              {[
                { label: 'Rows',    value: analysis.overview?.rows?.toLocaleString() },
                { label: 'Columns', value: analysis.overview?.cols },
                { label: 'Missing', value: `${analysis.overview?.missing_pct}%` },
                { label: 'Types',   value: Object.entries(analysis.overview?.type_counts ?? {}).map(([k,v]) => `${k}: ${v}`).join(' · ') },
              ].map(card => (
                <div key={card.label} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '14px 16px' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{card.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>{card.value}</div>
                </div>
              ))}
            </div>
          )}
          {!analysis && !loading && (
            <div style={{ padding: 40, textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', color: 'var(--muted)' }}>
              Click "Run analysis" to generate statistics for this dataset.
            </div>
          )}
          {numCols.length > 0 && (
            <section style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
                Numeric columns <span className="badge badge-numeric" style={{ marginLeft: 6 }}>{numCols.length}</span>
              </h2>
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                <table>
                  <thead><tr><th>Column</th><th>Count</th><th>Mean</th><th>Std</th><th>Min</th><th>Median</th><th>Max</th><th>Missing%</th></tr></thead>
                  <tbody>
                    {numCols.map(([col, s]: [string, any]) => (
                      <tr key={col}>
                        <td style={{ fontWeight: 600 }}>{col}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.count}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.mean?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.std?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.min?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.median?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.max?.toFixed(2)}</td>
                        <td style={{ color: s.missing_pct > 10 ? 'var(--danger)' : 'var(--muted)', fontFamily: 'var(--mono)' }}>{s.missing_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {catCols.length > 0 && (
            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
                Categorical columns <span className="badge badge-categorical" style={{ marginLeft: 6 }}>{catCols.length}</span>
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                {catCols.map(([col, s]: [string, any]) => (
                  <div key={col} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 14 }}>
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>{col} <span style={{ color: 'var(--muted)', fontSize: 12, fontWeight: 400 }}>({s.n_unique} unique)</span></div>
                    {(s.top_values ?? []).slice(0, 5).map((v: any) => (
                      <div key={v.value} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '2px 0', color: 'var(--muted)' }}>
                        <span style={{ color: 'var(--text)' }}>{v.value}</span>
                        <span style={{ fontFamily: 'var(--mono)' }}>{v.pct}%</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* ── Data tab ── */}
      {tab === 'data' && (
        <div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>

          {/* Left panel: Filters + CalcColumns */}
          <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>

            {/* Filters */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
                  Filters
                </span>
                <button className="btn btn-ghost btn-sm" onClick={addFilter} style={{ fontSize: 10, padding: '2px 7px' }}>
                  + Add
                </button>
              </div>

              {filterRows.length === 0 && (
                <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '6px 0' }}>No filters</p>
              )}

              {filterRows.map(f => (
                <div key={f.id} style={{ marginBottom: 8, background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, padding: 7 }}>
                  <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                    <select value={f.column} onChange={e => updateFilter(f.id, 'column', e.target.value)}
                      style={{ flex: 1, fontSize: 11, padding: '3px 4px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)', minWidth: 0 }}>
                      {allColNames.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <button onClick={() => removeFilter(f.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 14, padding: '0 2px', flexShrink: 0 }}>×</button>
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <select value={f.op} onChange={e => updateFilter(f.id, 'op', e.target.value)}
                      style={{ width: 90, fontSize: 11, padding: '3px 4px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }}>
                      {OPS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                    </select>
                    <input value={f.value} onChange={e => updateFilter(f.id, 'value', e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && applyFilters()}
                      placeholder="value…"
                      style={{ flex: 1, fontSize: 11, padding: '3px 6px', minWidth: 0 }} />
                  </div>
                </div>
              ))}

              {filterRows.length > 0 && (
                <button className="btn btn-primary btn-sm" onClick={applyFilters}
                  style={{ width: '100%', fontSize: 11, marginTop: 4 }}>
                  Apply Filters
                </button>
              )}
            </div>

            {/* Global Filter */}
            <div style={{ background: 'var(--surface)', border: `1px solid ${savedFilter ? 'var(--accent)' : 'var(--border)'}`, borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
                  Global Filter
                </span>
                {savedFilter && (
                  <span style={{ fontSize: 10, color: 'var(--accent)', padding: '1px 6px', background: 'rgba(99,102,241,.15)', borderRadius: 4 }}>
                    active
                  </span>
                )}
              </div>
              <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8, lineHeight: 1.5 }}>
                Applied to all reports that use this dataset.
              </p>
              <textarea
                value={filterExpr}
                onChange={e => { setFilterExpr(e.target.value); setFilterPreview(null) }}
                placeholder={"الفئة == 'ضابط' AND المرتب > 20000"}
                rows={3}
                style={{ width: '100%', fontSize: 11, fontFamily: 'var(--mono)', padding: '6px 8px',
                  background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4,
                  color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box', lineHeight: 1.6 }}
              />
              {filterPreview && (
                <div style={{ fontSize: 11, marginTop: 6, padding: '4px 8px', borderRadius: 4,
                  background: filterPreview.ok ? 'rgba(34,197,94,.1)' : 'rgba(239,68,68,.1)',
                  color: filterPreview.ok ? 'var(--success, #22c55e)' : 'var(--danger)' }}>
                  {filterPreview.ok
                    ? `✓ ${filterPreview.passing!.toLocaleString()} / ${filterPreview.total.toLocaleString()} rows pass`
                    : `✗ ${filterPreview.error}`}
                </div>
              )}
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                <button className="btn btn-ghost btn-sm"
                  style={{ fontSize: 11, flex: 1 }}
                  onClick={testGlobalFilter}
                  disabled={!filterExpr.trim()}>
                  Test
                </button>
                <button className="btn btn-primary btn-sm"
                  style={{ fontSize: 11, flex: 1 }}
                  onClick={() => saveGlobalFilter()}
                  disabled={filterSaving}>
                  {filterSaving ? 'Saving…' : 'Save'}
                </button>
                {savedFilter && (
                  <button className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, color: 'var(--danger)', padding: '4px 8px' }}
                    onClick={() => { setFilterExpr(''); saveGlobalFilter('') }}>
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* Calculated columns */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <CalcColumnsPanel
                datasetId={dsId}
                columns={ds.columns}
                onChanged={handleCalcColsChanged}
              />
            </div>
          </div>

          {/* Right panel: Data table */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            {/* Search bar */}
            <div style={{ marginBottom: 8, flexShrink: 0 }}>
              <input
                value={search}
                onChange={e => handleSearch(e.target.value)}
                placeholder="Search all columns…"
                style={{ width: '100%', fontSize: 12, padding: '6px 10px',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 6, color: 'var(--text)', boxSizing: 'border-box' }}
              />
            </div>

            {pvLoading && (
              <div style={{ textAlign: 'center', padding: 40, color: 'var(--muted)' }}>Loading data…</div>
            )}
            {!pvLoading && preview && (
              <>
                <div style={{ flex: 1, overflow: 'auto', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <table style={{ fontSize: 12 }}>
                    <thead>
                      <tr>
                        {preview.columns.map(c => {
                          const isSorted = sortBy === c
                          return (
                            <th key={c} style={{ whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none' }}
                              onClick={() => handleSort(c)}>
                              {calcColNames.has(c) && <span style={{ color: 'var(--accent)', marginRight: 4, fontSize: 10 }}>ƒx</span>}
                              {c}
                              <span style={{ marginLeft: 4, color: isSorted ? 'var(--accent)' : 'var(--border)', fontSize: 10 }}>
                                {isSorted ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
                              </span>
                            </th>
                          )
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, i) => (
                        <tr key={i}>
                          {(row as unknown[]).map((v, j) => (
                            <td key={j} style={{ fontFamily: typeof v === 'number' ? 'var(--mono)' : undefined }}>
                              {v == null ? <span style={{ color: 'var(--muted)' }}>—</span> : String(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', flexShrink: 0 }}>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, preview.total)} of {preview.total.toLocaleString()}
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                      disabled={page === 0}
                      onClick={() => { const p = page - 1; setPage(p); loadPreview(p, filterRows, calcCols, sortBy, sortDir, search) }}>
                      ← Prev
                    </button>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                      disabled={(page + 1) * PAGE_SIZE >= preview.total}
                      onClick={() => { const p = page + 1; setPage(p); loadPreview(p, filterRows, calcCols, sortBy, sortDir, search) }}>
                      Next →
                    </button>
                  </div>
                </div>
              </>
            )}
            {!pvLoading && pvError && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: 40 }}>
                <div style={{ fontSize: 32 }}>📂</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Dataset file not found</div>
                <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', maxWidth: 360 }}>{pvError}</div>
                {ds?.data_source_id && (ds?.source_table || ds?.source_query) ? (
                  <button className="btn btn-primary btn-sm" onClick={handleRefresh} disabled={refreshing}
                    style={{ marginTop: 8 }}>
                    {refreshing ? 'Refreshing…' : '↻ Refresh from source'}
                  </button>
                ) : ds?.data_source_id ? (
                  <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', maxWidth: 320 }}>
                    Original query not recorded.{' '}
                    <Link to="/connections" style={{ color: 'var(--accent)' }}>Re-import from Connections</Link>{' '}
                    to restore this dataset.
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>Re-upload the file to restore this dataset.</div>
                )}
              </div>
            )}
            {!pvLoading && !preview && !pvError && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 13 }}>
                Loading data…
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
