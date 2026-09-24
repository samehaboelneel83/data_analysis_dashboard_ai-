import { useCallback, useContext, useEffect, useState } from 'react'
import { navArrows, useDirection } from '../../contexts/DirectionContext'
import { dataPreviewApi } from '../../services/api'
import DataViewsBar from './DataViewsBar'
import { AuthContext } from '../../contexts/AuthContext'
import PrepStepsPanel from './PrepStepsPanel'

const PAGE_SIZE = 100

/**
 * The Data tab's grid, now an actual data browser: server-side paging,
 * click-to-sort column headers and a value search — all parameters the
 * data-preview endpoint always supported and this grid never used.
 */
export default function DataView({ datasetId, mode }: { datasetId: number; mode?: 'import' | 'directquery' }) {
  const arrows = navArrows(useDirection().rtl)
  // Only an admin may choose the data view applied to every new dataset. The
  // bar hides that control without this, so passing it is what makes the
  // setting reachable at all.
  const isAdmin = !!useContext(AuthContext)?.user?.role?.is_org_admin
  const [data, setData] = useState<{ columns: string[]; rows: unknown[][]; total: number } | null>(null)
  const [offset, setOffset] = useState(0)
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [search, setSearch] = useState('')
  const [searchDraft, setSearchDraft] = useState('')

  const load = useCallback(() => {
    dataPreviewApi.query(datasetId, [], [], PAGE_SIZE, offset, sortBy, sortDir,
      search || undefined).then(setData)
  }, [datasetId, offset, sortBy, sortDir, search])

  useEffect(() => { load() }, [load, mode])
  // Dataset switch resets the browsing state; a search/sort from the previous
  // dataset would silently filter the new one.
  useEffect(() => {
    setData(null); setOffset(0); setSortBy(undefined); setSortDir('asc')
    setSearch(''); setSearchDraft('')
  }, [datasetId])

  const toggleSort = (col: string) => {
    setOffset(0)
    if (sortBy !== col) { setSortBy(col); setSortDir('asc') }
    else if (sortDir === 'asc') setSortDir('desc')
    else { setSortBy(undefined); setSortDir('asc') }  // third click clears
  }

  const submitSearch = () => { setOffset(0); setSearch(searchDraft.trim()) }

  if (!data) return <p style={{ color: 'var(--muted)', padding: 16 }}>Loading…</p>

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%' }}>
      {mode !== 'directquery' && <DataViewsBar datasetId={datasetId} onApplied={load} isAdmin={isAdmin} />}
      <div style={{ display: 'flex', minHeight: 0, flex: 1 }}>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px 0' }}>
          <input value={searchDraft} onChange={e => setSearchDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submitSearch() }}
            placeholder="Search values…" aria-label="Search rows"
            style={{ fontSize: 12, width: 200 }} />
          <button className="btn" style={{ fontSize: 11 }} onClick={submitSearch}>Search</button>
          {search && (
            <button className="btn" style={{ fontSize: 11 }}
              onClick={() => { setSearchDraft(''); setSearch(''); setOffset(0) }}>
              ✕ Clear
            </button>
          )}
        </div>
        <div style={{ overflow: 'auto', padding: 12, flex: 1 }}>
          <table style={{ fontSize: 12 }}>
            <thead>
              <tr>
                {data.columns.map(c => (
                  <th key={c} onClick={() => toggleSort(c)} role="columnheader"
                    aria-sort={sortBy === c ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                    style={{ cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none' }}>
                    {c}{sortBy === c ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i}>{(row as unknown[]).map((v, j) => <td key={j}>{v == null ? '—' : String(v)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 12px', borderTop: '1px solid var(--border)' }}>
          <button className="btn" style={{ fontSize: 11 }} disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>{arrows.backChevron} Prev</button>
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>
            Page {page} of {pages} · {data.total.toLocaleString()} rows{search ? ' (filtered)' : ''}
          </span>
          <button className="btn" style={{ fontSize: 11 }} disabled={offset + PAGE_SIZE >= data.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}>Next {arrows.forwardChevron}</button>
        </div>
      </div>
      {/* Prep steps shape the frame this grid shows; DirectQuery data is shaped in
          SQL, so the editor only exists for import datasets. onPipelineChange
          refetches the grid so the effect of a step is visible immediately. */}
      {mode !== 'directquery' && (
        <PrepStepsPanel datasetId={datasetId} columns={data.columns} onPipelineChange={load} />
      )}
      </div>
    </div>
  )
}
