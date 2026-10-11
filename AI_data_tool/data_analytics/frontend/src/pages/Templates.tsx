import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { Copy, Eye, History, Pencil, Search, Star, Trash2 } from 'lucide-react'
import { datasetsApi, templatesApi, type Dataset, type TemplateCard } from '../services/api'
import type { Widget } from '../types/report'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import { styleVars } from '../lib/dashboardStyle'
import Thumb from './home/Thumb'
import UseTemplateDialog from './templates/UseTemplateDialog'
import SaveTemplateDialog from './templates/SaveTemplateDialog'
import { TemplatePreviewDialog, TemplateVersionsDialog } from './templates/TemplateDialogs'
import { categoryName, kindName, slotLabel, templateDescription, templateName } from './templates/words'
import './reports/dashboards.css'
import './templates/templates.css'

type Tab = 'all' | 'builtin' | 'org' | 'mine' | 'fav'
const TABS: Tab[] = ['all', 'builtin', 'org', 'mine', 'fav']

/**
 * The template gallery: the platform's templates, the organisation's and your
 * own, by kind, searchable, with favourites. Choosing a dataset ranks them by
 * how well each suits it (from its columns, never its rows). A template is
 * looked at on its own sample rows, then used: map your columns, get a
 * dashboard that is yours to change -- the template stays as it was.
 */
export default function Templates() {
  const t = useT()
  const confirm = useConfirm()
  const [cards, setCards] = useState<TemplateCard[] | null>(null)
  const [categories, setCategories] = useState<string[]>([])
  const [failed, setFailed] = useState(false)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState<number | null>(null)
  const [tab, setTab] = useState<Tab>('all')
  const [category, setCategory] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [using, setUsing] = useState<TemplateCard | null>(null)
  const [previewing, setPreviewing] = useState<TemplateCard | null>(null)
  const [editing, setEditing] = useState<TemplateCard | null>(null)
  const [versions, setVersions] = useState<TemplateCard | null>(null)

  const load = () => {
    templatesApi.list(datasetId)
      .then(got => { setCards(got.templates); setCategories(got.categories); setFailed(false) })
      .catch(() => { setCards([]); setFailed(true) })
  }
  useEffect(load, [datasetId])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { datasetsApi.list().then(setDatasets).catch(() => setDatasets([])) }, [])

  const shown = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    return (cards ?? []).filter(c => {
      if (tab === 'builtin' && c.source !== 'builtin') return false
      if (tab === 'org' && c.source !== 'org') return false
      if (tab === 'mine' && !c.mine) return false
      if (tab === 'fav' && !c.favorite) return false
      if (category && c.category !== category) return false
      if (!words.length) return true
      const text = [templateName(c, t), templateDescription(c, t), categoryName(c.category, t), ...c.tags,
        ...c.slots.map(s => slotLabel(s, t))].join(' ').toLowerCase()
      return words.every(w => text.includes(w))
    })
  }, [cards, tab, category, query, t])
  const best = datasetId != null ? shown.find(c => c.fit?.usable)?.ref : undefined

  const star = async (c: TemplateCard) => {
    setCards(cs => (cs ?? []).map(x => (x.ref === c.ref ? { ...x, favorite: !c.favorite } : x)))
    try { await templatesApi.favorite(c.ref, !c.favorite) } catch { load() }
  }
  const copy = async (c: TemplateCard) => {
    try {
      await templatesApi.save({ copy_of: c.ref, name: t('tpl.copyName', { name: templateName(c, t) }),
        description: templateDescription(c, t), category: c.category, tags: c.tags, visibility: 'personal' })
      toast.success(t('tpl.copied'))
      setTab('mine')
      load()
    } catch { toast.error(t('tpl.save.failed')) }
  }
  const remove = async (c: TemplateCard) => {
    if (!(await confirm({ title: t('tpl.delete.confirm', { name: c.name }), confirmLabel: t('tpl.delete') }))) return
    try { await templatesApi.delete(Number(c.ref.slice(2))); toast.success(t('tpl.deleted')); load() }
    catch { toast.error(t('tpl.save.failed')) }
  }

  return (
    <div className="tpl-page">
      <header className="tpl-head">
        <h1>{t('tpl.title')}</h1>
        <p>{t('tpl.sub')}</p>
      </header>

      <div className="tpl-bar">
        <div className="tpl-search">
          <Search size={16} aria-hidden />
          <input className="dsh-in" type="search" value={query} onChange={e => setQuery(e.target.value)} dir="auto"
            aria-label={t('tpl.search')} placeholder={t('tpl.searchPh')} />
        </div>
        <div className="tpl-data">
          <select className="dsh-in" aria-label={t('tpl.forData')} value={datasetId ?? ''}
            onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">{t('tpl.forData')}: {t('tpl.forData.none')}</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
      </div>
      <p className="tpl-help">{t('tpl.forData.help')}</p>

      <div className="tpl-tabs" role="group" aria-label={t('tpl.title')}>
        {TABS.map(k => (
          <button key={k} type="button" className="tpl-chip" aria-pressed={tab === k} onClick={() => setTab(k)}>
            {k === 'fav' && <Star size={13} aria-hidden />}{t(`tpl.tab.${k}`)}
          </button>
        ))}
      </div>
      <div className="tpl-tabs" role="group" aria-label={t('tpl.save.category')}>
        <button type="button" className="tpl-chip" aria-pressed={category === null} onClick={() => setCategory(null)}>{t('tpl.cat.all')}</button>
        {categories.map(c => (
          <button key={c} type="button" className="tpl-chip" aria-pressed={category === c} onClick={() => setCategory(c)}>{categoryName(c, t)}</button>
        ))}
      </div>

      {failed && <p className="tpl-empty" role="alert">{t('tpl.loadFailed')}</p>}
      {cards === null && <p className="tpl-empty">{t('common.loading')}</p>}
      {cards !== null && !failed && shown.length === 0 && (
        <p className="tpl-empty">{t(tab === 'mine' ? 'tpl.empty.mine' : 'tpl.empty')}</p>
      )}

      <div className="tpl-grid" data-testid="template-grid">
        {shown.map(c => {
          const name = templateName(c, t)
          const needs = c.slots.filter(s => s.required)
          return (
            <article key={c.ref} className="tpl-card" aria-label={name} data-testid={`template-${c.ref}`}>
              <div className="tpl-art" style={{ ...styleVars(c.style), background: 'var(--dl-s-page-bg, var(--surface2))' }}>
                <Thumb widgets={c.preview.map((b, i) => ({ id: i, widget_type: b.kind, layout: b }) as unknown as Widget)} />
                {best === c.ref && <span className="tpl-best">{t('tpl.fit.best')}</span>}
                <button type="button" className="tpl-star" aria-pressed={c.favorite} onClick={() => void star(c)}
                  aria-label={t(c.favorite ? 'tpl.fav.remove' : 'tpl.fav.add', { name })} title={t('tpl.star')}>
                  <Star size={15} aria-hidden fill={c.favorite ? 'currentColor' : 'none'} />
                </button>
              </div>
              <div className="tpl-body">
                <h3 dir="auto">{name}</h3>
                <p dir="auto">{templateDescription(c, t)}</p>
                <div className="tpl-meta">
                  <span className="tpl-badge">{categoryName(c.category, t)}</span>
                  <span className="tpl-badge">{t(`tpl.src.${c.source}`)}</span>
                  <span>{t('tpl.count', { n: localDigits(String(c.widgets)) })}</span>
                  {c.pages > 1 && <span>{t('tpl.pages', { n: localDigits(String(c.pages)) })}</span>}
                  {c.source !== 'builtin' && <span>{t('tpl.version', { n: localDigits(String(c.version)) })}</span>}
                </div>
                {needs.length > 0 && (
                  <div className="tpl-needs"><b>{t('tpl.needs')}:</b> {needs.map(s => kindName(s.kind, t)).join(' · ')}</div>
                )}
                {c.fit && (
                  <div className="tpl-fit" data-usable={c.fit.usable}>
                    {c.fit.usable ? (
                      <>
                        <span>{c.fit.widgets.kept === c.fit.widgets.total
                          ? t('tpl.fit.all', { n: localDigits(String(c.fit.widgets.total)) })
                          : t('tpl.fit.some', { kept: localDigits(String(c.fit.widgets.kept)), n: localDigits(String(c.fit.widgets.total)) })}</span>
                        <span className="bar" aria-hidden><i style={{ width: `${Math.round(c.fit.score * 100)}%` }} /></span>
                        {c.fit.elsewhere && (
                          <span style={{ color: 'var(--muted)' }}>{t('tpl.fit.elsewhere', {
                            n: localDigits(String(c.fit.elsewhere.widgets)), names: c.fit.elsewhere.datasets.join(', ') })}</span>
                        )}
                      </>
                    ) : (
                      <span>{t('tpl.fit.no')}{c.fit.missing.length > 0 && ` — ${t('tpl.fit.missing', {
                        what: c.slots.filter(s => s.required && c.fit!.missing.includes(s.id)).map(s => slotLabel(s, t)).join(' · ') })}`}</span>
                    )}
                  </div>
                )}
              </div>
              <div className="tpl-foot">
                <button type="button" className="tpl-ib" onClick={() => setPreviewing(c)} aria-label={`${t('tpl.preview')}: ${name}`} title={t('tpl.preview')}><Eye size={15} aria-hidden /></button>
                <button type="button" className="tpl-ib" onClick={() => void copy(c)} aria-label={`${t('tpl.copy')}: ${name}`} title={t('tpl.copy')}><Copy size={15} aria-hidden /></button>
                {c.source !== 'builtin' && (
                  <button type="button" className="tpl-ib" onClick={() => setVersions(c)} aria-label={`${t('tpl.versions')}: ${name}`} title={t('tpl.versions')}><History size={15} aria-hidden /></button>
                )}
                {c.can_change && (
                  <>
                    <button type="button" className="tpl-ib" onClick={() => setEditing(c)} aria-label={`${t('tpl.editDetails')}: ${name}`} title={t('tpl.editDetails')}><Pencil size={15} aria-hidden /></button>
                    <button type="button" className="tpl-ib" onClick={() => void remove(c)} aria-label={`${t('tpl.delete')}: ${name}`} title={t('tpl.delete')}><Trash2 size={15} aria-hidden /></button>
                  </>
                )}
                <span className="sp" />
                <button type="button" className="btn btn-primary btn-sm" disabled={c.fit ? !c.fit.usable : false} onClick={() => setUsing(c)}>{t('tpl.use')}</button>
              </div>
            </article>
          )
        })}
      </div>

      {using && <UseTemplateDialog template={using} datasetId={datasetId} onClose={() => setUsing(null)} />}
      {previewing && <TemplatePreviewDialog template={previewing} onClose={() => setPreviewing(null)}
        onUse={() => { setUsing(previewing); setPreviewing(null) }} />}
      {editing && <SaveTemplateDialog editing={editing} onClose={() => setEditing(null)} onSaved={load} />}
      {versions && <TemplateVersionsDialog template={versions} onClose={() => setVersions(null)} onRestored={load} />}
    </div>
  )
}
