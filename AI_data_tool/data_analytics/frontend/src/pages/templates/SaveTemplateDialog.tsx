import { useState } from 'react'
import toast from 'react-hot-toast'
import { X } from 'lucide-react'
import { templatesApi, type TemplateCard, type TemplateLeftOut } from '../../services/api'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { useT, type TranslateFn } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { categoryName } from './words'

export const TEMPLATE_CATEGORIES = ['overview', 'trend', 'comparison', 'stages', 'target', 'monitoring', 'geography',
  'distribution', 'detail'] as const

/** What a saved template does not carry, in one sentence; empty when it carries everything. */
export function leftOutText(left: TemplateLeftOut | undefined, t: TranslateFn): string {
  const parts: string[] = []
  if (left?.filters) parts.push(t('tpl.save.left.filters', { n: localDigits(String(left.filters)) }))
  if (left?.rules) parts.push(t('tpl.save.left.rules', { n: localDigits(String(left.rules)) }))
  if (left?.unknown?.length) parts.push(t('tpl.save.left.unknown', { names: left.unknown.join(', ') }))
  return parts.length ? t('tpl.save.left', { what: parts.join(' · ') }) : ''
}

/**
 * Save a dashboard as a template (`reportId`), or change a saved template's
 * details (`editing`). Saving never changes the dashboard; editing details
 * never changes the template's content.
 */
export default function SaveTemplateDialog({ reportId, defaultName, editing, onClose, onSaved }: {
  reportId?: number
  defaultName?: string
  editing?: TemplateCard
  onClose: () => void
  onSaved?: (card: TemplateCard) => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [name, setName] = useState(editing?.name ?? defaultName ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')
  const [category, setCategory] = useState<string>(editing?.category ?? 'overview')
  const [tags, setTags] = useState((editing?.tags ?? []).join(', '))
  const [visibility, setVisibility] = useState<'personal' | 'org'>(editing?.source === 'org' ? 'org' : 'personal')
  const [busy, setBusy] = useState(false)

  const save = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    const body = { name: name.trim(), description: description.trim(), category, visibility,
      tags: tags.split(/[,،]/).map(x => x.trim()).filter(Boolean) }
    try {
      const card = editing
        ? await templatesApi.edit(Number(editing.ref.slice(2)), body)
        : await templatesApi.save({ ...body, report_id: reportId })
      const left = leftOutText(card.left_out, t)
      toast.success(left ? `${t('tpl.save.saved')} ${left}` : t('tpl.save.saved'), { duration: left ? 9000 : 3000 })
      onSaved?.(card)
      onClose()
    } catch {
      toast.error(t('tpl.save.failed'))
      setBusy(false)
    }
  }

  return (
    <div className="dsh-scrim">
      <div ref={ref} className="dsh-dlg" role="dialog" aria-modal="true" aria-labelledby="tpl-save-t">
        <div className="dsh-dh">
          <div className="tt">
            <h2 id="tpl-save-t">{t(editing ? 'tpl.edit.title' : 'tpl.save.title')}</h2>
            {!editing && <p>{t('tpl.save.sub')}</p>}
          </div>
          <button type="button" className="dsh-ib" onClick={onClose} aria-label={t('tpl.close')} title={t('tpl.close')}><X size={16} aria-hidden /></button>
        </div>
        <div className="dsh-db">
          <label className="dsh-lbl" htmlFor="tpl-save-name">{t('tpl.save.name')}</label>
          <input id="tpl-save-name" className="dsh-in" value={name} onChange={e => setName(e.target.value)} dir="auto" maxLength={120} autoFocus />
          <label className="dsh-lbl" htmlFor="tpl-save-desc" style={{ marginTop: 14 }}>{t('tpl.save.desc')}</label>
          <textarea id="tpl-save-desc" className="dsh-in ta" value={description} onChange={e => setDescription(e.target.value)} dir="auto"
            maxLength={500} placeholder={t('tpl.save.descPh')} />
          <div className="tpl-row2" style={{ marginTop: 14 }}>
            <div>
              <label className="dsh-lbl" htmlFor="tpl-save-cat">{t('tpl.save.category')}</label>
              <select id="tpl-save-cat" className="dsh-in" value={category} onChange={e => setCategory(e.target.value)}>
                {TEMPLATE_CATEGORIES.map(c => <option key={c} value={c}>{categoryName(c, t)}</option>)}
              </select>
            </div>
            <div>
              <label className="dsh-lbl" htmlFor="tpl-save-who">{t('tpl.save.who')}</label>
              <select id="tpl-save-who" className="dsh-in" value={visibility} onChange={e => setVisibility(e.target.value as 'personal' | 'org')}>
                <option value="personal">{t('tpl.save.personal')}</option>
                <option value="org">{t('tpl.save.org')}</option>
              </select>
            </div>
          </div>
          <label className="dsh-lbl" htmlFor="tpl-save-tags" style={{ marginTop: 14 }}>{t('tpl.save.tags')}</label>
          <input id="tpl-save-tags" className="dsh-in" value={tags} onChange={e => setTags(e.target.value)} dir="auto" placeholder={t('tpl.save.tagsPh')} />
        </div>
        <div className="dsh-df">
          <span className="dsh-sp" />
          <button type="button" className="btn btn-ghost dsh-btn-line" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary" disabled={busy || !name.trim()} onClick={() => void save()}>
            {t(editing ? 'tpl.edit.save' : 'tpl.save.do')}
          </button>
        </div>
      </div>
    </div>
  )
}
