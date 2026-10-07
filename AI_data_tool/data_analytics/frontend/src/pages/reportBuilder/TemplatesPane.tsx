import { useEffect, useState, type ReactNode } from 'react'
import toast from 'react-hot-toast'
import { Plus, Trash2 } from 'lucide-react'
import { pageTemplatesApi, reportsApi } from '../../services/api'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { TEMPLATE_NAMES, TemplateArt } from '../reports/dialogs'
import Thumb from '../home/Thumb'

/**
 * The left panel's Templates tab (redesign 7e2), after the prototype's cards:
 * page layouts to start a page from, each with a schematic and "Add page".
 * Everything v1 offered behind the page tabs' ▾ menu is here too -- your saved
 * page templates (deletable), importing a page from another dashboard and
 * saving the open page -- and v1's widget templates follow underneath.
 */
export default function TemplatesPane({ reportId, activePageId, onAdded, widgetTemplates }: {
  reportId: number
  activePageId: number | null
  onAdded: () => void
  /** v1's saved widget templates (state lives in the builder). */
  widgetTemplates?: ReactNode
}) {
  const t = useT()
  const confirm = useConfirm()
  const [builtins, setBuiltins] = useState<{ key: string; name: string; widgets: number }[] | null>(null)
  const [saved, setSaved] = useState<{ id: number; name: string; widgets: number }[]>([])
  const [naming, setNaming] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [reports, setReports] = useState<{ id: number; name: string }[]>([])
  const [source, setSource] = useState<{ id: number; pages: { id: number; name: string }[] } | null>(null)

  useEffect(() => {
    pageTemplatesApi.builtins().then(setBuiltins).catch(() => setBuiltins([]))
    pageTemplatesApi.list().then(setSaved).catch(() => {})
    Promise.resolve().then(() => reportsApi.list())
      .then(list => setReports((list ?? []).filter(r => r.id !== reportId))).catch(() => {})
  }, [reportId])

  const add = async (src: Parameters<typeof pageTemplatesApi.addFrom>[1]) => {
    setBusy(true)
    try { await pageTemplatesApi.addFrom(reportId, src); onAdded() }
    catch { toast.error(t('bd.tpl.addFailed')) }
    finally { setBusy(false) }
  }
  const n = (k: number) => t(k === 1 ? 'bd.tpl.widget' : 'bd.tpl.widgets', { n: localDigits(String(k)) })

  return (
    <div className="dl-bd-tpls">
      <h3 className="dl-bd-gh">{t('bd.tpl.layouts')}</h3>
      {builtins === null && <p className="dl-bd-note">{t('common.loading')}</p>}
      {builtins?.map(b => (
        <article key={b.key} className="dl-bd-tpl">
          <div className="th"><TemplateArt k={b.key} /></div>
          <div className="r">
            <div className="tx"><b>{TEMPLATE_NAMES[b.key] ? t(TEMPLATE_NAMES[b.key]) : b.name}</b><small>{n(b.widgets)}</small></div>
            <button type="button" className="btn btn-ghost btn-sm dl-bd-line" disabled={busy}
              aria-label={`${t('bd.tpl.addPage')}: ${TEMPLATE_NAMES[b.key] ? t(TEMPLATE_NAMES[b.key]) : b.name}`}
              onClick={() => void add({ builtin: b.key })}><Plus size={13} aria-hidden />{t('bd.tpl.addPage')}</button>
          </div>
        </article>
      ))}

      {saved.length > 0 && <h3 className="dl-bd-gh">{t('bd.tpl.yours')}</h3>}
      {saved.map(s => (
        <article key={s.id} className="dl-bd-tpl">
          <div className="th"><Thumb widgets={[]} /></div>
          <div className="r">
            <div className="tx"><b><bdi>{s.name}</bdi></b><small>{n(s.widgets)}</small></div>
            <button type="button" className="dl-bd-ib" aria-label={`Delete template ${s.name}`} title={t('bd.tpl.delete')}
              onClick={async () => {
                if (!await confirm({ title: t('bd.tpl.deleteTitle', { name: s.name }), body: t('bd.tpl.deleteBody'), confirmLabel: t('bd.tpl.deleteBtn') })) return
                try { await pageTemplatesApi.delete(s.id); setSaved(l => l.filter(x => x.id !== s.id)) }
                catch { toast.error(t('bd.tpl.deleteFailed')) }
              }}><Trash2 size={14} aria-hidden /></button>
            <button type="button" className="btn btn-ghost btn-sm dl-bd-line" disabled={busy}
              aria-label={`${t('bd.tpl.addPage')}: ${s.name}`}
              onClick={() => void add({ template_id: s.id })}><Plus size={13} aria-hidden />{t('bd.tpl.addPage')}</button>
          </div>
        </article>
      ))}

      {activePageId != null && (naming === null ? (
        <button type="button" className="btn btn-ghost btn-sm dl-bd-dashed" onClick={() => setNaming('')}>
          <Plus size={13} aria-hidden />{t('bd.tpl.saveThis')}
        </button>
      ) : (
        <div className="dl-bd-tplsave">
          <input aria-label="New template name" autoFocus value={naming} dir="auto" placeholder={t('bd.tpl.namePh')}
            onChange={e => setNaming(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') setNaming(null) }} />
          <button type="button" className="btn btn-primary btn-sm" aria-label="Save page template" disabled={!naming.trim()}
            onClick={() => {
              const name = naming.trim()
              pageTemplatesApi.saveFrom(reportId, activePageId, name)
                .then(() => {
                  toast.success(t('bd.tpl.saved', { name })); setNaming(null)
                  pageTemplatesApi.list().then(setSaved).catch(() => {})
                })
                .catch(() => toast.error(t('bd.tpl.saveFailed')))
            }}>{t('bd.tpl.saveBtn')}</button>
        </div>
      ))}

      {reports.length > 0 && (<>
        <h3 className="dl-bd-gh">{t('bd.tpl.import')}</h3>
        <select aria-label="Source report" className="dl-bd-in" value={source?.id ?? ''}
          onChange={e => {
            const id = Number(e.target.value)
            if (!id) { setSource(null); return }
            reportsApi.get(id).then(r => setSource({ id, pages: r.pages.map(p => ({ id: p.id, name: p.name })) })).catch(() => {})
          }}>
          <option value="">{t('bd.tpl.chooseReport')}</option>
          {reports.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        {source?.pages.map(p => (
          <button key={p.id} type="button" className="dl-bd-imp" disabled={busy}
            onClick={() => void add({ source_report_id: source.id, source_page_id: p.id })}>
            <Plus size={13} aria-hidden /><bdi>{p.name}</bdi>
          </button>
        ))}
      </>)}

      {widgetTemplates && (<>
        <h3 className="dl-bd-gh">{t('bd.tpl.widgetsHead')}</h3>
        {widgetTemplates}
      </>)}
    </div>
  )
}
