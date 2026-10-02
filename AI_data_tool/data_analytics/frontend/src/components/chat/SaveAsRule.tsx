/**
 * "Save as a business rule" (3.8). A definition typed into the chat --
 * "current employees means to_date = 9999-01-01", "by headcount I mean
 * distinct emp_no" -- used to live for one answer and be gone. Offered under
 * the message that gives it; saving writes a glossary term with a rule the
 * agent applies to every later question on this connection.
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import { BookOpen } from 'lucide-react'
import { metadataApi } from '../../services/api'
import { useT } from '../../i18n'

const CUE = /\b(means?|i mean|is defined as|defined as|counts? as|should (?:be|count|mean)|refers? to|definition of|always (?:use|count|exclude|include))\b|(?:يعني|أقصد|المقصود|تعني|تعريف|يُقصد|يقصد)/i
const SPLIT = /\s*(?:\bmeans?\b|\bis defined as\b|\bcounts? as\b|\brefers? to\b|\bshould (?:be|mean)\b|يعني|تعني|المقصود ب|=)\s*/i

/** Whether a message reads like a definition worth keeping. */
export function looksLikeDefinition(text: string): boolean {
  const s = (text ?? '').trim()
  return s.length >= 8 && s.length <= 600 && CUE.test(s)
}

/** The term being defined: the words before "means" (or the Arabic cue). */
export function definedTerm(text: string): string {
  const s = (text ?? '').trim()
  const byMean = /^(?:by|when i say)\s+["'“]?(.+?)["'”]?\s*,?\s+i mean\b/i.exec(s)
  if (byMean) return byMean[1].trim().slice(0, 60)
  const parts = s.split(SPLIT)
  if (parts.length < 2) return ''
  const head = parts[0].replace(/^(by|when i say|note:?|rule:?|عندما أقول|بـ?)\s+/i, '').replace(/["'“”]/g, '').trim()
  return head.length > 0 && head.length <= 60 ? head : ''
}

export default function SaveAsRule({ sourceId, text }: { sourceId: number; text: string }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)
  const [term, setTerm] = useState(() => definedTerm(text))
  const [rule, setRule] = useState(text.trim())
  const [always, setAlways] = useState(true)
  const [busy, setBusy] = useState(false)
  if (saved) return <span className="dl-save-rule__done" style={{ fontSize: 11, color: 'var(--muted)' }}>{t('chat.ruleSaved')}</span>
  if (!open) {
    return (
      <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={() => setOpen(true)}>
        <BookOpen size={12} aria-hidden /> {t('chat.saveRule')}
      </button>
    )
  }
  const save = async () => {
    if (!term.trim() || !rule.trim()) return
    setBusy(true)
    try {
      await metadataApi.addTerm(sourceId, { term: term.trim(), definition: rule.trim(), rule: rule.trim(), always })
      setSaved(true)
      toast.success(t('chat.ruleSavedToast', { term: term.trim() }))
    } catch {
      toast.error(t('chat.ruleSaveFailed'))
    } finally { setBusy(false) }
  }
  return (
    <div role="group" aria-label={t('chat.saveRule')} style={{ display: 'grid', gap: 6, fontSize: 12, marginTop: 6,
      border: '1px solid var(--border)', borderRadius: 6, padding: 8, background: 'var(--surface2)' }}>
      <input aria-label={t('chat.ruleTerm')} placeholder={t('chat.ruleTerm')} value={term}
        onChange={e => setTerm(e.target.value)} dir="auto" />
      <textarea aria-label={t('chat.ruleText')} value={rule} rows={2}
        onChange={e => setRule(e.target.value)} dir="auto" />
      <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input type="checkbox" checked={always} onChange={e => setAlways(e.target.checked)} />
        {t('chat.ruleAlways')}
      </label>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" className="btn btn-primary btn-sm" disabled={busy || !term.trim() || !rule.trim()}
          onClick={() => void save()}>{t('chat.ruleSave')}</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>{t('common.cancel')}</button>
      </div>
    </div>
  )
}
