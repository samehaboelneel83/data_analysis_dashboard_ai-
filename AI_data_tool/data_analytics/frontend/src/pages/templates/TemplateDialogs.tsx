import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { X } from 'lucide-react'
import { templatesApi, type TemplateCard } from '../../services/api'
import type { Widget } from '../../types/report'
import type { DashboardStyle } from '../../lib/dashboardStyle'
import { styleVars } from '../../lib/dashboardStyle'
import { useModalDialog } from '../../components/ui/useModalDialog'
import WidgetRenderer from '../../components/report/WidgetRenderer'
import { CrossFilterProvider } from '../../components/report/CrossFilterContext'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { formatDate } from '../../lib/dateFormat'
import { templateName } from './words'

const CELL = 56

/** The template drawn on its own sample rows: what it looks like, before any
 *  dataset is chosen. The charts are real ones; the rows are placeholders. */
export function TemplatePreviewDialog({ template, onClose, onUse }: {
  template: TemplateCard
  onClose: () => void
  onUse: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [got, setGot] = useState<{ rows: number; style: DashboardStyle; pages: { name: string; widgets: (Widget & { data: unknown })[] }[] } | null>(null)
  const [failed, setFailed] = useState(false)
  const [page, setPage] = useState(0)
  useEffect(() => { templatesApi.preview(template.ref).then(setGot).catch(() => setFailed(true)) }, [template.ref])
  // On a phone the twelve columns are too narrow to read: the charts are
  // stacked full width in reading order (row, then column), as a shared
  // dashboard is.
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.innerWidth < 720)
  useEffect(() => {
    const on = () => setNarrow(window.innerWidth < 720)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  const placed = got?.pages[page]?.widgets ?? []
  const widgets = narrow ? [...placed].sort((a, b) => (a.layout?.y ?? 0) - (b.layout?.y ?? 0) || (a.layout?.x ?? 0) - (b.layout?.x ?? 0)) : placed
  const height = Math.max(240, ...widgets.map(w => ((w.layout?.y ?? 0) + (w.layout?.h ?? 4)) * CELL + 12))
  return (
    <div className="dsh-scrim">
      <div ref={ref} className="dsh-dlg" style={{ width: 'min(1180px, 100%)' }} role="dialog" aria-modal="true" aria-labelledby="tpl-pv-t">
        <div className="dsh-dh">
          <div className="tt">
            <h2 id="tpl-pv-t">{t('tpl.preview.title', { name: templateName(template, t) })}</h2>
            {got && <p>{t('tpl.preview.note', { n: localDigits(got.rows.toLocaleString('en-US')) })}</p>}
          </div>
          <button type="button" className="dsh-ib" onClick={onClose} aria-label={t('tpl.close')} title={t('tpl.close')}><X size={16} aria-hidden /></button>
        </div>
        <div className="dsh-db">
          {failed && <p className="dsh-note" role="alert">{t('tpl.preview.failed')}</p>}
          {!got && !failed && <p className="dsh-note">{t('common.loading')}</p>}
          {got && got.pages.length > 1 && (
            <div className="tpl-pv-tabs" role="tablist" aria-label={t('tpl.preview.page')}>
              {got.pages.map((p, i) => (
                <button key={i} type="button" role="tab" aria-selected={i === page} className="tpl-chip" aria-pressed={i === page} onClick={() => setPage(i)}>
                  <bdi>{p.name}</bdi>
                </button>
              ))}
            </div>
          )}
          {got && (
            <CrossFilterProvider widgets={widgets}>
              <div className="tpl-pv" data-testid="template-preview"
                style={{ ...(narrow ? { display: 'flex', flexDirection: 'column', gap: 8, padding: 8 } : { height }),
                  ...styleVars(got.style), background: 'var(--dl-s-page-bg, var(--surface2))', borderRadius: 12 }}>
                {widgets.map(w => (
                  <div key={w.id} style={narrow
                    ? { height: Math.max(150, Math.min((w.layout?.h ?? 4) * CELL, 320)) }
                    : { position: 'absolute', insetInlineStart: `${((w.layout?.x ?? 0) / 12) * 100}%`,
                        top: (w.layout?.y ?? 0) * CELL, width: `${((w.layout?.w ?? 6) / 12) * 100}%`,
                        height: (w.layout?.h ?? 4) * CELL, padding: 6 }}>
                    <WidgetRenderer widget={w} datasetId={0} dataOverride={w.data} editMode={false} allowExport={false}
                      onSelect={() => {}} selected={false} />
                  </div>
                ))}
              </div>
            </CrossFilterProvider>
          )}
        </div>
        <div className="dsh-df">
          <span className="dsh-sp" />
          <button type="button" className="btn btn-ghost dsh-btn-line" onClick={onClose}>{t('tpl.close')}</button>
          <button type="button" className="btn btn-primary" onClick={onUse}>{t('tpl.use')}</button>
        </div>
      </div>
    </div>
  )
}

/** A saved template's earlier versions; restoring one makes a new version. */
export function TemplateVersionsDialog({ template, onClose, onRestored }: {
  template: TemplateCard
  onClose: () => void
  onRestored: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const id = Number(template.ref.slice(2))
  const [got, setGot] = useState<Awaited<ReturnType<typeof templatesApi.versions>> | null>(null)
  const load = () => { templatesApi.versions(id).then(setGot).catch(() => setGot({ current: template.version, versions: [] })) }
  useEffect(load, [id])  // eslint-disable-line react-hooks/exhaustive-deps
  const restore = async (versionId: number, n: number) => {
    try {
      await templatesApi.restore(id, versionId)
      toast.success(t('tpl.ver.restored', { n: localDigits(String(n)) }))
      onRestored()
      load()
    } catch { toast.error(t('tpl.ver.failed')) }
  }
  return (
    <div className="dsh-scrim">
      <div ref={ref} className="dsh-dlg sm" role="dialog" aria-modal="true" aria-labelledby="tpl-ver-t">
        <div className="dsh-dh">
          <div className="tt">
            <h2 id="tpl-ver-t">{t('tpl.ver.title', { name: template.name })}</h2>
            {got && <p>{t('tpl.ver.current', { n: localDigits(String(got.current)) })}</p>}
          </div>
          <button type="button" className="dsh-ib" onClick={onClose} aria-label={t('tpl.close')} title={t('tpl.close')}><X size={16} aria-hidden /></button>
        </div>
        <div className="dsh-db">
          {!got ? <p className="dsh-note">{t('common.loading')}</p>
            : got.versions.length === 0 ? <p className="dsh-note">{t('tpl.ver.none')}</p>
            : (
              <ul className="tpl-vers" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {got.versions.map(v => (
                  <li key={v.id}>
                    <span>
                      {t('tpl.ver.row', { n: localDigits(String(v.version)), charts: localDigits(String(v.widgets)) })}
                      <small>{v.created_at ? formatDate(v.created_at) : ''}{v.note ? ` · ${v.note}` : ''}</small>
                    </span>
                    {template.can_change && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => void restore(v.id, v.version)}>{t('tpl.ver.restore')}</button>
                    )}
                  </li>
                ))}
              </ul>
            )}
        </div>
        <div className="dsh-df">
          <span className="dsh-sp" />
          <button type="button" className="btn btn-ghost dsh-btn-line" onClick={onClose}>{t('tpl.close')}</button>
        </div>
      </div>
    </div>
  )
}
