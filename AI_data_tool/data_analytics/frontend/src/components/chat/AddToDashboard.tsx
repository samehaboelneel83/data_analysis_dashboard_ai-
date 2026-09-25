import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { LayoutDashboard, Plus } from 'lucide-react'
import { reportsApi } from '../../services/api'
import type { Report } from '../../types/report'
import { useT } from '../../i18n'
import type { WidgetDraft } from './answerWidget'

/**
 * "Add to dashboard" for one answer: pick a dashboard built on this dataset,
 * or start a new one. The widget is the report engine's own (dimension +
 * measure + aggregation) -- it re-queries the dataset live, it is not a
 * picture of this answer -- which is why answerWidget only offers a draft
 * when the answer maps cleanly onto the dataset's columns.
 */
export default function AddToDashboard({ datasetId, draft, title }: {
  datasetId: number
  draft: WidgetDraft
  title: string
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [reports, setReports] = useState<Report[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [added, setAdded] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    if (reports === null) {
      reportsApi.list()
        .then(all => setReports(all.filter(r => r.dataset_id === datasetId)))
        .catch(() => setReports([]))
    }
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, reports, datasetId])

  const add = async (reportId: number | null) => {
    setBusy(true)
    try {
      const report = reportId == null
        ? await reportsApi.create({ name: title.slice(0, 80) || t('ask.newDash'), dataset_id: datasetId })
        : await reportsApi.get(reportId)
      const pageId = report.pages?.[0]?.id
      if (pageId == null) throw new Error('This dashboard has no page to add to.')
      await reportsApi.addWidget(report.id, pageId, {
        widget_type: draft.widget_type, title: title.slice(0, 120),
        config: draft.config,
        layout: { x: 0, y: 999, w: draft.widget_type === 'kpi' ? 3 : 6, h: draft.widget_type === 'kpi' ? 3 : 5 },
      } as never)
      setAdded(report.id)
      setOpen(false)
      toast.success(t('ask.addedTo', { name: report.name }))
    } catch (e) {
      toast.error((e as Error)?.message || t('ask.addFailed'))
    } finally {
      setBusy(false)
    }
  }

  if (added != null) {
    return (
      <Link to={`/reports/${added}`} className="dl-act dl-act--done">
        <LayoutDashboard size={14} aria-hidden /> {t('ask.openDash')}
      </Link>
    )
  }

  return (
    <div className="dl-addash" ref={ref}>
      <button type="button" className="dl-act dl-act--primary" aria-haspopup="menu" aria-expanded={open}
        disabled={busy} onClick={() => setOpen(o => !o)}>
        <LayoutDashboard size={14} aria-hidden /> {busy ? t('ask.adding') : t('ask.addDash')}
      </button>
      {open && (
        <div className="dl-addash__menu" role="menu" aria-label={t('ask.addDash')}>
          {reports === null && <div className="dl-addash__note">{t('common.loading')}</div>}
          {reports?.map(r => (
            <button key={r.id} type="button" role="menuitem" className="dl-addash__item"
              onClick={() => void add(r.id)}>
              <LayoutDashboard size={14} aria-hidden /> <span>{r.name}</span>
            </button>
          ))}
          {reports !== null && reports.length > 0 && <div className="dl-addash__sep" role="separator" />}
          <button type="button" role="menuitem" className="dl-addash__item" onClick={() => void add(null)}>
            <Plus size={14} aria-hidden /> <span>{t('ask.newDash')}</span>
          </button>
        </div>
      )}
    </div>
  )
}
