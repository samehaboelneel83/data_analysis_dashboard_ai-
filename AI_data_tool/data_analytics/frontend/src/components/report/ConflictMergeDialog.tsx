/**
 * E09: combine an edit with a colleague's instead of choosing one of them.
 *
 * Opened from the edit-conflict banner. Settings only one of the two changed
 * are combined without a question (lib/threeWayMerge.ts); each setting both
 * changed is listed with their value and yours, and nothing is saved until
 * every one has a choice. Saving sends the combined widget against the
 * revision the conflict reported, so a third edit in the meantime is itself
 * a conflict rather than lost.
 */
import { useMemo, useState } from 'react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { mergeWidgetEdits, resolveMerge, type WidgetEdit } from '../../lib/threeWayMerge'
import { useModalDialog } from '../ui/useModalDialog'

/** A setting's value as one short line: what a person can compare at a glance. */
function shown(v: unknown): string {
  if (v === undefined || v === null || v === '') return '—'
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return s.length > 80 ? s.slice(0, 77) + '…' : s
}

export default function ConflictMergeDialog({ base, theirs, mine, changedBy, onSave, onClose }: {
  base: WidgetEdit
  theirs: WidgetEdit
  mine: WidgetEdit
  changedBy: string | null
  onSave: (edit: WidgetEdit) => void
  onClose: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const result = useMemo(() => mergeWidgetEdits(base, theirs, mine), [base, theirs, mine])
  const [choices, setChoices] = useState<Record<string, 'mine' | 'theirs'>>({})
  const settled = result.conflicts.every(c => choices[c.key])
  const label = (key: string) => key === 'title' ? t('conflict.field.title')
    : key === 'widget_type' ? t('conflict.field.type') : key.replace(/_/g, ' ')
  const who = changedBy ?? t('conflict.someone')

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t('conflict.title')} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', width: 'min(620px, 100%)',
          maxHeight: 'min(640px, 90vh)', display: 'flex', flexDirection: 'column', boxShadow: '0 12px 40px rgba(0,0,0,.25)' }}>
        <div style={{ padding: '16px 16px 8px' }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>{t('conflict.title')}</div>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }} data-testid="merge-summary">
            {t('conflict.auto', { mine: localDigits(String(result.fromMine)),
                                  theirs: localDigits(String(result.fromTheirs)), who })}
            {' '}{result.conflicts.length ? t('conflict.both', { who }) : t('conflict.none')}
          </p>
        </div>
        <div style={{ overflowY: 'auto', padding: '4px 16px 8px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {result.conflicts.map(c => (
            <fieldset key={c.key} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', margin: 0 }}>
              <legend style={{ fontSize: 12, fontWeight: 700, padding: '0 4px' }}>{label(c.key)}</legend>
              {(['theirs', 'mine'] as const).map(side => (
                <label key={side} style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 12, padding: '2px 0', cursor: 'pointer' }}>
                  <input type="radio" name={`merge-${c.key}`} checked={choices[c.key] === side}
                    onChange={() => setChoices(ch => ({ ...ch, [c.key]: side }))} />
                  <span style={{ minWidth: 70, color: 'var(--muted)' }}>
                    {side === 'theirs' ? t('conflict.theirs', { who }) : t('conflict.mine')}
                  </span>
                  <code dir="auto" style={{ fontSize: 11.5, overflowWrap: 'anywhere' }}>{shown(side === 'theirs' ? c.theirs : c.mine)}</code>
                </label>
              ))}
            </fieldset>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '10px 16px', borderTop: '1px solid var(--border)', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!settled}
            onClick={() => onSave(resolveMerge(result, choices))}>{t('conflict.saveCombined')}</button>
        </div>
      </div>
    </div>
  )
}
