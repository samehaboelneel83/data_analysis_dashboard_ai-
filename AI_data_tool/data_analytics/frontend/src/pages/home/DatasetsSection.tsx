import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  BarChartBig, Database, Eye, FileJson, FileSpreadsheet, FileText, Layers, Plug, Sparkles, Upload, X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { formatTimeAgo, useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { reportsApi, type DatasetSummary, type LineageGraph } from '../../services/api'
import DatasetPreview from '../datasetsList/DatasetPreview'
import { sourceKind, sourceWords, statusOf } from '../datasetsList/classify'
import '../datasetsList/datasetsList.css'
import { Empty, SecHead, Sk } from './parts'

/**
 * Home's Datasets table (redesign 7a): the five most recently changed, with
 * where each comes from, its size and how current it is -- the same words
 * and the same lineage health the Datasets list uses (classify.ts).
 */

const SHOWN = 5
const ltr = (s: string) => `⁦${s}⁩`
const fmtBytes = (b: number) => b < 1024 ? ltr(`${b} B`) : b < 1024 ** 2 ? ltr(`${(b / 1024).toFixed(1)} KB`) : ltr(`${(b / 1024 ** 2).toFixed(1)} MB`)

/** Datasets Ask AI can answer from: an upload, or a live dataset with its connection. */
export const askable = (d: DatasetSummary) => !!d.filename || (d.mode === 'directquery' && d.data_source_id != null)

const changedAt = (d: DatasetSummary) => new Date(d.last_refreshed_at ?? d.created_at ?? 0).getTime()
export const recentDatasets = (ds: DatasetSummary[]) => [...ds].sort((a, b) => changedAt(b) - changedAt(a))

function SourceIcon({ d }: { d: DatasetSummary }) {
  const kind = sourceKind(d)
  if (kind === 'derived') return <span className="hm-src s-der" aria-hidden><Layers size={17} /></span>
  if (kind !== 'upload') return <span className="hm-src s-db" aria-hidden><Database size={17} /></span>
  const ext = (d.filename ?? '').split('.').pop()?.toLowerCase()
  if (ext === 'xlsx' || ext === 'xls') return <span className="hm-src s-xls" aria-hidden><FileSpreadsheet size={17} /></span>
  if (ext === 'json') return <span className="hm-src s-csv" aria-hidden><FileJson size={17} /></span>
  return <span className="hm-src s-csv" aria-hidden><FileText size={17} /></span>
}

function PreviewDrawer({ ds, graph, meId, onClose }: {
  ds: DatasetSummary; graph: LineageGraph | null; meId: number | null; onClose: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  return (
    <>
      <div className="hm-drawer-scrim" onClick={onClose} />
      <div ref={ref} className="hm-drawer" role="dialog" aria-modal="true" aria-label={t('hm.ds.previewOf', { name: ds.name })}>
        <div className="hm-drawer__close">
          <button type="button" className="hm-ib" onClick={onClose} aria-label={t('hm.close')} title={t('hm.close')}><X size={15} aria-hidden /></button>
        </div>
        <DatasetPreview ds={ds} graph={graph} meId={meId} fmtBytes={fmtBytes} />
      </div>
    </>
  )
}

export default function DatasetsSection({ datasets, graph, graphFailed, onRetryGraph, loading, meId, onOpen }: {
  datasets: DatasetSummary[]
  graph: LineageGraph | null
  graphFailed: boolean
  onRetryGraph: () => void
  loading: boolean
  meId: number | null
  onOpen: () => void
}) {
  const t = useT()
  const navigate = useNavigate()
  const [preview, setPreview] = useState<DatasetSummary | null>(null)
  const [building, setBuilding] = useState<number | null>(null)

  const build = async (d: DatasetSummary) => {
    setBuilding(d.id)
    try {
      const r = await reportsApi.create({ name: d.name, dataset_id: d.id })
      onOpen()
      navigate(`/reports/${(r as { id: number }).id}?edit=1`)
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('dsl.pv.buildFailed'))
      setBuilding(null)
    }
  }

  const head = <SecHead id="hm-data" title={t('nav.datasets')} count={loading ? undefined : datasets.length}
    all={!loading && datasets.length ? '/datasets' : undefined} />

  if (!loading && !datasets.length) {
    return (
      <section className="hm-sec" aria-labelledby="hm-data">{head}
        <Empty icon={Database} title={t('hm.ds.empty')} text={t('hm.ds.emptyText')} actions={<>
          <Link className="btn btn-primary btn-sm" to="/upload"><Upload size={14} aria-hidden />{t('hm.qa.upload')}</Link>
          <Link className="btn btn-ghost btn-sm" to="/connections"><Plug size={14} aria-hidden />{t('hm.qa.connect')}</Link>
        </>} />
      </section>
    )
  }

  const lin = (id: number) => graph?.datasets.find(x => x.id === id)
  const freshness = (d: DatasetSummary): { tone: string; label: string } => {
    const kind = sourceKind(d)
    if (kind === 'live') return { tone: 'ok', label: t('hm.fr.live') }
    const s = statusOf(d, lin(d.id))
    if (s === 'failing') return { tone: 'err', label: t('hm.fr.failing') }
    if (s === 'stale') return { tone: 'warn', label: t('hm.fr.stale') }
    if (kind === 'upload') return { tone: '', label: t('hm.fr.uploaded') }
    return { tone: 'ok', label: t('hm.fr.fresh') }
  }
  const size = (d: DatasetSummary) => d.mode === 'directquery'
    ? t('home.colsOnly', { cols: localDigits((d.col_count ?? 0).toLocaleString('en-US')) })
    : ltr(localDigits(`${(d.row_count ?? 0).toLocaleString('en-US')} × ${(d.col_count ?? 0).toLocaleString('en-US')}`))

  const rows = loading
    ? [0, 1, 2, 3, 4].map(i => (
      <tr key={i}>
        <td><div className="hm-nm"><Sk w="34px" h={34} r={9} style={{ flex: 'none' }} /><div style={{ flex: 1 }}><Sk w="70%" h={12} /><Sk w="30%" h={10} style={{ marginTop: 6 }} /></div></div></td>
        <td><Sk w="60px" h={10} /></td><td><Sk w="80px" h={10} /></td><td><Sk w="70px" h={10} /></td><td />
      </tr>
    ))
    : recentDatasets(datasets).slice(0, SHOWN).map(d => {
      const f = freshness(d)
      const when = formatTimeAgo(lin(d.id)?.load.last_refreshed_at ?? d.last_refreshed_at ?? d.created_at, t)
      return (
        <tr key={d.id} data-testid={`home-dataset-${d.id}`}>
          <td>
            <div className="hm-nm"><SourceIcon d={d} />
              <div>
                <Link className="hm-rl" to={`/datasets/${d.id}`} title={d.name}
                  onClick={e => { if (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) onOpen() }}><bdi>{d.name}</bdi></Link>
                <small>{sourceWords(d, graph, t)}</small>
              </div>
            </div>
          </td>
          <td className="num">{size(d)}</td>
          <td className="nw">{when ?? '—'}</td>
          <td><span className="hm-fr"><span className={`hm-dot ${f.tone}`} aria-hidden />{f.label}</span></td>
          <td>
            <div className="hm-ra">
              <button type="button" className="hm-ib" onClick={() => setPreview(d)}
                aria-label={t('hm.ds.previewName', { name: d.name })} title={t('hm.ds.preview')}><Eye size={15} aria-hidden /></button>
              <button type="button" className="hm-ib" onClick={() => void build(d)} disabled={building === d.id}
                aria-label={t('hm.ds.buildName', { name: d.name })} title={t('hm.ds.build')}><BarChartBig size={15} aria-hidden /></button>
              {askable(d) && (
                <Link className="hm-ib" to={`/ask?dataset=${d.id}`}
                  aria-label={t('hm.ds.askName', { name: d.name })} title={t('nav.askAi')}><Sparkles size={15} aria-hidden /></Link>
              )}
            </div>
          </td>
        </tr>
      )
    })

  return (
    <section className="hm-sec" aria-labelledby="hm-data" data-testid="home-datasets">
      {head}
      <div className="hm-tbw">
        <table className="hm-tb">
          <thead><tr>
            <th>{t('hm.col.name')}</th><th>{t('hm.col.size')}</th><th>{t('hm.col.refreshed')}</th><th>{t('hm.col.freshness')}</th>
            <th style={{ width: '1%' }}><span className="dl-sr-only">{t('hm.col.actions')}</span></th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {graphFailed && !loading && (
        <p className="hm-note" role="status">{t('hm.ds.healthFailed')}<button type="button" onClick={onRetryGraph}>{t('hm.retry')}</button></p>
      )}
      {preview && <PreviewDrawer ds={preview} graph={graph} meId={meId} onClose={() => setPreview(null)} />}
    </section>
  )
}
