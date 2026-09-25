import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { datasetsApi, DatasetSummary } from '../services/api'
import {
  ChevronLeft, ChevronRight, Database, HardDrive, Link2, Plug, Plus, Rows,
  Sparkles, Trash2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useConfirm } from '../components/ui/ConfirmDialog'
import SuggestDashboardsDialog from '../components/dataset/SuggestDashboardsDialog'
import ActionMenu from '../components/ActionMenu'
import { useListFilter } from '../components/ui/ListFilter'
import IconLabel from '../components/ui/IconLabel'
import LoadError from '../components/ui/LoadError'
import { useT } from '../i18n'
import BulkBar from '../components/ui/BulkBar'
import { useBulkSelection } from '../lib/useBulkSelection'
import { looksLikeTestData } from '../lib/testData'

/**
 * The dataset inventory.
 *
 * The page's whole job is scanning: find one dataset among dozens, judge its
 * shape and age, act on it. So the table is the page, and everything above it
 * is sized to stay out of its way.
 *
 * Deliberately absent: the demo seeder (a setup chore, not data management --
 * it is a CLI job now) and the personal pinned-tile dashboard (this is an
 * inventory of your data, not a second dashboard). Both APIs survive, and
 * Dashboard.test.tsx pins both absences so neither returns by accident.
 */

/**
 * A file size, kept in reading order in RTL too.
 *
 * "25.0 KB" is a number followed by a Latin unit. Dropped into an RTL
 * paragraph, the bidi algorithm reorders that run and it renders as "KB 25.0"
 * -- which is what the Arabic Datasets table was showing. U+2066 LEFT-TO-RIGHT
 * ISOLATE (…U+2069 POP) wraps the pair as one neutral-directional chunk, so it
 * stays "25.0 KB" while the CELL still aligns to the right of an RTL table.
 * Same treatment every mixed number+unit string on this page needs.
 */
const ltr = (s: string) => `⁦${s}⁩`

function fmtBytes(b: number) {
  if (b < 1024) return ltr(`${b} B`)
  if (b < 1024 ** 2) return ltr(`${(b / 1024).toFixed(1)} KB`)
  return ltr(`${(b / 1024 ** 2).toFixed(1)} MB`)
}

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * A DirectQuery dataset keeps its rows in the connection: the platform stores
 * none of them and measures no bytes. Printing "0" and "0 B" states something
 * false about the data, so those two figures read as an em dash instead.
 *
 * Only for DirectQuery. An imported file with no rows genuinely has none, and
 * dashing that would hide a failed upload behind tidy punctuation.
 */
const NOT_APPLICABLE = '—'
const storesItsOwnRows = (d: DatasetSummary) => d.mode !== 'directquery'

/**
 * Rows per page.
 *
 * CLIENT-SIDE, and it has to be: `GET /datasets` accepts no page, page_size,
 * limit or offset, and answers with a bare array carrying no total (see
 * `routers/datasets.py::list_datasets`). It also filters by readability in
 * Python AFTER the query, so a SQL LIMIT would page the wrong set. Until the
 * endpoint grows those parameters and a count, the browser already holds every
 * row and slices what it shows.
 */
const PAGE_SIZES = [8, 25, 50] as const
const DEFAULT_PAGE_SIZE = PAGE_SIZES[0]
// Per-viewer, per-browser: a convenience, not a setting anyone else sees.
const PAGE_SIZE_KEY = 'datalytics:datasets-page-size'
function storedPageSize(): number {
  try {
    const n = Number(localStorage.getItem(PAGE_SIZE_KEY))
    return (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE
  } catch { return DEFAULT_PAGE_SIZE }
}

export default function Dashboard() {
  const t = useT()
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  // Which dataset the suggestion panel is open for, if any. Held here rather
  // than in the row so the panel survives the list re-rendering underneath it.
  const [suggestFor, setSuggestFor] = useState<{ id: number; name: string } | null>(null)
  const dsFilter = useListFilter(datasets,
    d => [d.name, d.description], t('search.datasets'))
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [page, setPage] = useState(1)
  // 8 by default (BUG-031 asked for more; the default stays so the list reads
  // the same for everyone until they choose otherwise).
  const [pageSize, setPageSizeState] = useState(storedPageSize)
  const setPageSize = (n: number) => {
    setPageSizeState(n)
    setPage(1)
    try { localStorage.setItem(PAGE_SIZE_KEY, String(n)) } catch { /* private window */ }
  }

  // This is the landing page, and it had no `.catch` at all: an outage left an
  // unhandled rejection and rendered "No datasets yet" -- telling a user with a
  // full workspace that they have nothing, and inviting them to re-import data
  // that already exists.
  const load = () => {
    setLoadError(null)
    datasetsApi.list()
      .then(setDatasets)
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const confirm = useConfirm()

  const handleDelete = async (id: number, name: string) => {
    if (!await confirm({ title: `Delete "${name}"?`, body: 'This cannot be undone.' })) return
    await datasetsApi.delete(id)
    setDatasets(d => d.filter(x => x.id !== id))
    toast.success('Dataset deleted')
  }

  // Several at once: clearing out a batch of test uploads used to be one
  // menu, one dialog, one toast per dataset.
  const bulk = useBulkSelection<DatasetSummary>({
    remove: id => datasetsApi.delete(id),
    onRemoved: ids => setDatasets(d => d.filter(x => !ids.includes(x.id))),
    noun: t('noun.datasets'),
  })
  const testLike = datasets.filter(d => looksLikeTestData(d.name))

  const rows = dsFilter.filtered
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  // Narrowing the search must not strand you on page 5 of a two-page result,
  // looking at an empty table. Clamping here rather than in an effect keeps it
  // a pure function of the current query -- an effect would render the empty
  // page once before correcting it.
  const current = Math.min(page, pageCount)
  const start = (current - 1) * pageSize
  const visible = rows.slice(start, start + pageSize)
  // Deliberately NOT in the URL: this route documents no query parameters and
  // the deep links into it (from Home, from the rail) depend on that.
  useEffect(() => { setPage(1) }, [dsFilter.query])

  const pageNumbers = useMemo(
    () => Array.from({ length: pageCount }, (_, i) => i + 1),
    [pageCount],
  )

  const stats = [
    { key: 'datasets', icon: Database, label: t('datasets.stat.datasets'),
      value: datasets.length.toLocaleString() },
    { key: 'rows', icon: Rows, label: t('datasets.stat.rows'),
      value: datasets.reduce((n, d) => n + (d.row_count ?? 0), 0).toLocaleString() },
    // Columns are deliberately not totalled: summing the column counts of two
    // unrelated tables describes no quantity anybody uses.
    { key: 'stored', icon: HardDrive, label: t('datasets.stat.stored'),
      value: fmtBytes(datasets.reduce((n, d) => n + (d.file_size ?? 0), 0)) },
  ]

  return (
    <div>
      <header className="dl-page-head">
        <div>
          <h1 className="dl-page-head__title">{t('nav.datasets')}</h1>
          <p className="dl-page-head__sub">{t('datasets.subtitle')}</p>
        </div>
        <Link to="/upload" className="btn btn-primary">
          <Plus size={16} /> {t('datasets.upload')}
        </Link>
      </header>

      {loading && <p className="dl-muted-line">{t('common.loading')}</p>}

      {/* At-a-glance totals, derived from the list already in memory -- no
          extra request, and nothing here can disagree with the table below it,
          which a separate stats endpoint eventually would. Hidden while the
          list is empty, where "0 datasets · 0 rows" is noise above an empty
          state that says it better. */}
      {!loading && !loadError && datasets.length > 0 && (
        <section aria-label={t('datasets.summary')} className="dl-stats">
          {stats.map(s => (
            <div key={s.key} data-testid={`stat-${s.key}`} className="card dl-stat">
              <span className={`dl-stat__icon dl-stat__icon--${s.key}`} aria-hidden>
                <s.icon size={20} />
              </span>
              <div>
                <div className="dl-stat__label">{s.label}</div>
                <div data-figure className="dl-stat__figure">{s.value}</div>
              </div>
            </div>
          ))}
        </section>
      )}

      {!loading && loadError != null && (
        <LoadError what="your datasets" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && datasets.length === 0 && (
        <div className="card dl-empty">
          <Database size={40} className="dl-empty__icon" aria-hidden />
          <p className="dl-empty__title">{t('datasets.empty.title')}</p>
          <p className="dl-empty__body">
            {t('datasets.empty.body')}
          </p>
          <div className="dl-empty__actions">
            <Link to="/upload" className="btn btn-primary">{t('datasets.empty.upload')}</Link>
            <Link to="/connections" className="btn btn-ghost">{t('datasets.empty.connect')}</Link>
          </div>
        </div>
      )}

      {datasets.length > 0 && (
        <>
          {/* The search box sits with the table it filters, not up in the page
              header beside an action that creates datasets rather than finds
              them. */}
          <div className="dl-toolbar">
            {dsFilter.input}
            {rows.length !== datasets.length && (
              <span className="dl-toolbar__count">
                {t('common.countOf', { n: rows.length.toLocaleString(), total: datasets.length.toLocaleString() })}
              </span>
            )}
            {testLike.length > 0 && (
              <button type="button" className="dl-select-hint" style={{ marginInlineStart: 'auto' }}
                onClick={() => bulk.setMany(testLike.map(d => d.id), true)}>
                <Trash2 size={13} aria-hidden /> {t('bulk.selectTest', { n: testLike.length })}
              </button>
            )}
          </div>
          <BulkBar count={bulk.selected.size} busy={bulk.busy} noun={t('noun.datasets')}
            onClear={bulk.clear} onDelete={() => void bulk.deleteSelected(datasets)} />

          {dsFilter.noMatches ? (
            <p className="dl-nomatch">{t('common.nothingMatches', { q: dsFilter.query })}</p>
          ) : (
            <div className="card dl-table-card">
              <table className="dl-table">
                <thead>
                  <tr>
                    <th className="dl-table__check">
                      <input type="checkbox" aria-label={t('bulk.selectAll')}
                        checked={visible.length > 0 && visible.every(d => bulk.selected.has(d.id))}
                        ref={el => { if (el) el.indeterminate = visible.some(d => bulk.selected.has(d.id)) && !visible.every(d => bulk.selected.has(d.id)) }}
                        onChange={e => bulk.setMany(visible.map(d => d.id), e.target.checked)} />
                    </th>
                    <th>{t('datasets.col.name')}</th>
                    {/* Numbers align end-ward so digits line up in a column; the
                        logical property keeps that correct in RTL, where "end" is
                        the left. */}
                    <th className="dl-table__num">{t('datasets.col.rows')}</th>
                    <th className="dl-table__num">{t('datasets.col.columns')}</th>
                    <th className="dl-table__num">{t('datasets.col.size')}</th>
                    <th>{t('datasets.col.created')}</th>
                    <th className="dl-table__actions" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {visible.map(ds => (
                    <tr key={ds.id} data-selected={bulk.selected.has(ds.id) || undefined}>
                      <td className="dl-table__check">
                        <input type="checkbox" aria-label={t('bulk.selectRow', { name: ds.name })}
                          checked={bulk.selected.has(ds.id)} onChange={() => bulk.toggle(ds.id)} />
                      </td>
                      <td>
                        <div className="dl-cell-name">
                          <Link to={`/datasets/${ds.id}`} className="row-name">{ds.name}</Link>
                          {ds.mode === 'directquery' && (
                            /* No tooltip saying "zero": this dataset's rows and
                               bytes are UNKNOWN, not none, and the em dashes in
                               those cells say exactly that. */
                            <span className="dl-chip dl-chip--live"
                              title="Queried live from its connection — nothing is stored here">
                              <IconLabel icon={Plug} size={12}>{t('datasets.live')}</IconLabel>
                            </span>
                          )}
                          {ds.shared && (
                            <span className="dl-chip dl-chip--shared"
                              title="Shared with you by an org admin">
                              <IconLabel icon={Link2} size={12}>{t('datasets.shared')}</IconLabel>
                            </span>
                          )}
                        </div>
                        {ds.description && (
                          <div className="dl-cell-sub">{ds.description}</div>
                        )}
                      </td>
                      <td className="dl-table__num">
                        {storesItsOwnRows(ds) ? ds.row_count.toLocaleString() : NOT_APPLICABLE}
                      </td>
                      <td className="dl-table__num">{ds.col_count.toLocaleString()}</td>
                      <td className="dl-table__num">
                        {storesItsOwnRows(ds) ? fmtBytes(ds.file_size) : NOT_APPLICABLE}
                      </td>
                      <td className="dl-table__date">{fmtDate(ds.created_at)}</td>
                      <td className="dl-table__actions">
                        {/* One way in. A red trash icon repeated down every row
                            is an alarm the page rings at itself; delete already
                            lived in this menu, and lives there alone now. */}
                        <ActionMenu
                          label={`More actions for dataset ${ds.name}`}
                          items={[
                            { key: 'suggest', label: t('datasets.suggest'), icon: <Sparkles size={16} />, onSelect: () => setSuggestFor({ id: ds.id, name: ds.name }) },
                            { key: 'delete', label: t('datasets.delete'), danger: true, icon: <Trash2 size={16} />, onSelect: () => handleDelete(ds.id, ds.name) },
                          ]}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Inside the table card, because it describes the table rather
                  than the page. Previous and Next are DISABLED at the ends
                  rather than removed: a control that vanishes moves everything
                  beside it, and the reader has to work out whether they ran
                  out of pages or lost a button. */}
              <nav className="dl-pager" aria-label={t('pager.aria')}>
                <span className="dl-pager__info">
                  {t('pager.showing', { from: (start + 1).toLocaleString(),
                    to: Math.min(start + pageSize, rows.length).toLocaleString(),
                    total: rows.length.toLocaleString() })}
                </span>
                <label className="dl-pager__info" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  {t('pager.perPage')}
                  <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
                    style={{ width: 'auto', padding: '2px 6px' }}>
                    {PAGE_SIZES.map(n => <option key={n} value={n}>{n.toLocaleString()}</option>)}
                  </select>
                </label>
                <div className="dl-pager__controls">
                  <button type="button" className="dl-pager__btn"
                    onClick={() => setPage(current - 1)} disabled={current === 1}>
                    <ChevronLeft size={16} className="dl-pager__icon" aria-hidden />
                    {t('pager.previous')}
                  </button>
                  {pageNumbers.map(n => (
                    <button key={n} type="button" className="dl-pager__btn"
                      aria-current={n === current ? 'page' : undefined}
                      aria-label={t('pager.page', { n })}
                      onClick={() => setPage(n)}>
                      {n.toLocaleString()}
                    </button>
                  ))}
                  <button type="button" className="dl-pager__btn"
                    onClick={() => setPage(current + 1)} disabled={current === pageCount}>
                    {t('pager.next')}
                    <ChevronRight size={16} className="dl-pager__icon" aria-hidden />
                  </button>
                </div>
              </nav>
            </div>
          )}
        </>
      )}

      {suggestFor && (
        <SuggestDashboardsDialog
          datasetId={suggestFor.id} datasetName={suggestFor.name}
          onClose={() => setSuggestFor(null)} />
      )}
    </div>
  )
}
