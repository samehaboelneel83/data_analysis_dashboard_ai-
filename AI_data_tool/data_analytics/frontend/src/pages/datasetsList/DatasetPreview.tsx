import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LayoutGrid } from 'lucide-react'
import toast from 'react-hot-toast'
import { useDirection } from '../../contexts/DirectionContext'
import { useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { isCertified } from '../../lib/cleanDatasets'
import { formatCell } from '../../lib/displayNumber'
import { dataPreviewApi, reportsApi, sensitivityApi, type DatasetSummary, type LineageGraph } from '../../services/api'
import { dashboardsOf, sourceKind } from './classify'

const TYPE_TAG: Record<string, string> = { numeric: 'NUM', datetime: 'DATE', categorical: 'TXT', boolean: 'BOOL', text: 'TXT' }
const MAX_CHIPS = 8
const PREVIEW_ROWS = 4
const PREVIEW_COLS = 3

/**
 * The selected dataset, at a glance (redesign step 3a): what it is, its facts,
 * its columns, its first rows and the dashboards built on it, with the three
 * things a reader does next. Facts the backend does not return (the owner's
 * name for someone else's dataset, a period) are left out, not stubbed.
 */
export default function DatasetPreview({ ds, graph, meId, fmtBytes }: {
  ds: DatasetSummary | null
  graph: LineageGraph | null
  meId: number | null
  fmtBytes: (b: number) => string
}) {
  const t = useT()
  const navigate = useNavigate()
  const { language } = useDirection()
  const [rows, setRows] = useState<{ columns: string[]; rows: unknown[][] } | null>(null)
  const [label, setLabel] = useState<string | null | undefined>(undefined)
  const [building, setBuilding] = useState(false)
  const id = ds?.id

  useEffect(() => {
    setRows(null); setLabel(undefined)
    if (id == null) return
    let live = true
    Promise.resolve().then(() => dataPreviewApi?.query?.(id, [], [], PREVIEW_ROWS, 0))
      .then(r => { if (live && r) setRows({ columns: r.columns, rows: r.rows }) }).catch(() => {})
    Promise.resolve().then(() => sensitivityApi?.get?.(id))
      .then(r => { if (live && r) setLabel(r.effective ?? r.label ?? null) }).catch(() => {})
    return () => { live = false }
  }, [id])

  if (!ds) {
    return <aside className="dl-dsl__preview dl-dsl__preview--empty" aria-label={t('dsl.pv.aria')}>{t('dsl.pv.select')}</aside>
  }

  const kind = sourceKind(ds)
  const dashboards = dashboardsOf(ds.id, graph)
  const cols = ds.columns ?? []
  const stores = ds.mode !== 'directquery'
  const meta = [
    ds.created_by != null && ds.created_by === meId ? t('dsl.pv.byYou') : null,
    stores ? fmtBytes(ds.file_size) : null,
    isCertified(ds) ? t('dsl.pv.certified') : t('dsl.pv.notCertified'),
  ].filter(Boolean).join(' · ')

  const build = async () => {
    setBuilding(true)
    try {
      const report = await reportsApi.create({ name: ds.name, dataset_id: ds.id })
      navigate(`/reports/${(report as { id: number }).id}?edit=1`)
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('dsl.pv.buildFailed'))
      setBuilding(false)
    }
  }

  const shownCols = rows ? rows.columns.slice(0, PREVIEW_COLS) : []
  return (
    <aside className="dl-dsl__preview" aria-label={t('dsl.pv.aria')} data-testid="dataset-preview">
      <div className="dl-dsl__eyebrow">{t('dsl.pv.kind', { kind: t(`dsl.src.${kind}` as MessageKey) })}</div>
      <h2 className="dl-dsl__pv-title">{ds.name}</h2>
      <div className="dl-dsl__pv-meta">{meta}</div>
      <div className="dl-dsl__pv-actions">
        <Link to={`/datasets/${ds.id}`} className="btn btn-primary btn-sm">{t('dsl.pv.open')}</Link>
        <button type="button" className="btn btn-sm" disabled={building} onClick={() => void build()}>
          {building ? t('dsl.pv.building') : t('dsl.pv.build')}
        </button>
        <Link to={`/ask?dataset=${ds.id}`} className="btn btn-sm">{t('dsl.pv.ask')}</Link>
      </div>

      <dl className="dl-dsl__facts">
        <div><dt>{t('dsl.pv.rows')}</dt><dd>{stores || ds.row_count ? localDigits(ds.row_count.toLocaleString('en-US')) : '—'}</dd></div>
        <div><dt>{t('dsl.pv.columns')}</dt><dd>{localDigits(String(ds.col_count))}</dd></div>
        <div><dt>{kind === 'upload' ? t('dsl.pv.uploaded') : t('dsl.pv.created')}</dt>
          <dd className="dl-dsl__fact-sm">{localDigits(new Date(ds.created_at).toLocaleString(language === 'ar' ? 'ar-u-nu-latn' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }))}</dd></div>
        <div><dt>{t('dsl.pv.label')}</dt>
          <dd className="dl-dsl__fact-sm">{label === undefined ? '…' : label ?? t('dsl.pv.noLabel')}</dd></div>
      </dl>

      {cols.length > 0 && (
        <section>
          <h3 className="dl-dsl__pv-h">{t('dsl.pv.columnsN', { n: localDigits(String(cols.length)) })}</h3>
          <div className="dl-dsl__chips">
            {cols.slice(0, MAX_CHIPS).map(c => (
              <span key={c.name} className="dl-dsl__chip" dir="ltr">
                <span className="dl-dsl__chip-tag">{TYPE_TAG[c.dtype] ?? c.dtype.slice(0, 4).toUpperCase()}</span>{c.name}
              </span>
            ))}
            {cols.length > MAX_CHIPS && <span className="dl-dsl__chip">+{localDigits(String(cols.length - MAX_CHIPS))}</span>}
          </div>
        </section>
      )}

      {rows && rows.rows.length > 0 && (
        <section>
          <h3 className="dl-dsl__pv-h">{t('dsl.pv.firstRows')}</h3>
          <table className="dl-dsl__pv-table">
            <thead><tr>{shownCols.map(c => <th key={c} dir="auto">{c}</th>)}</tr></thead>
            <tbody>
              {rows.rows.map((r, i) => (
                <tr key={i}>{shownCols.map((_, j) => {
                  const v = r[j]
                  return <td key={j} dir="auto" className={typeof v === 'number' ? 'dl-dsl__num' : undefined}>
                    {formatCell(v as string | number | boolean | null)}
                  </td>
                })}</tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {dashboards && (
        <section>
          <h3 className="dl-dsl__pv-h">{t('dsl.pv.dashboards')}</h3>
          {dashboards.length === 0
            ? <p className="dl-dsl__pv-none">{t('dsl.pv.noDashboards')}</p>
            : (
              <ul className="dl-dsl__pv-list">
                {dashboards.slice(0, 5).map(r => (
                  <li key={r.id}><Link to={`/reports/${r.id}`}><LayoutGrid size={14} aria-hidden /> {r.name}</Link></li>
                ))}
              </ul>
            )}
        </section>
      )}
    </aside>
  )
}
