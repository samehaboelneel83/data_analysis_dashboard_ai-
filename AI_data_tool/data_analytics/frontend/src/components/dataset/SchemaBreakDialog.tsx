/**
 * E05: a refresh the server refused because the source no longer has columns
 * something on this dataset uses (409 `schema_break`). The file on disk is
 * still the last good one; this is where the person decides what happens
 * next. Each missing column gets a picker of the incoming columns, preset to
 * the server's likely match -- a source that only RENAMED a column refreshes
 * with nothing broken. "Refresh anyway" is the knowing break.
 */
import { useT } from '../../i18n'
import { useState } from 'react'
import { useModalDialog } from '../ui/useModalDialog'

export interface SchemaBreak {
  detail: string
  missing: string[]
  suggestions: Record<string, string[]>
  available: string[]
  dependents: Record<string, { kind: string; label: string }[]>
}

export function isSchemaBreak(data: unknown): data is SchemaBreak {
  return !!data && typeof data === 'object' && (data as { code?: unknown }).code === 'schema_break'
}

export default function SchemaBreakDialog({ info, onMap, onForce, onClose }: {
  info: SchemaBreak
  /** new column name -> the old name everything uses */
  onMap: (columnMap: Record<string, string>) => void
  /** Refresh anyway, still applying whichever names were picked. */
  onForce: (columnMap: Record<string, string>) => void
  onClose: () => void
}) {
  const t9 = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [choice, setChoice] = useState<Record<string, string>>(() =>
    Object.fromEntries(info.missing.map(m => [m, info.suggestions[m]?.[0] ?? ''])))
  const chosen = Object.entries(choice).filter(([, fresh]) => fresh)
  const columnMap = Object.fromEntries(chosen.map(([old, fresh]) => [fresh, old]))
  const allMapped = chosen.length === info.missing.length
  const usedTwice = new Set(chosen.map(([, f]) => f)).size !== chosen.length

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t9('sb.aria')} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', width: 'min(560px, 100%)',
          maxHeight: 'min(620px, 90vh)', display: 'flex', flexDirection: 'column', boxShadow: '0 12px 40px rgba(0,0,0,.25)' }}>
        <div style={{ padding: '16px 16px 8px' }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>{t9('sb.title')}</div>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>
            {t9('sb.body')}
          </p>
        </div>
        <div style={{ overflowY: 'auto', padding: '4px 16px 8px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {info.missing.map(m => {
            const uses = info.dependents[m] ?? []
            return (
              <div key={m}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong style={{ fontSize: 13 }}>{m}</strong>
                  <span style={{ color: 'var(--muted)', fontSize: 12 }}>{t9('sb.isNow')}</span>
                  <select aria-label={t9('sb.newNameFor', { c: m })} value={choice[m] ?? ''}
                    onChange={e => setChoice(c => ({ ...c, [m]: e.target.value }))}
                    style={{ width: 'auto', padding: '2px 6px' }}>
                    <option value="">{t9('sb.gone')}</option>
                    {info.available.map(a => <option key={a} value={a}>{a}</option>)}
                  </select>
                </label>
                {uses.length > 0 && (
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>
                    {t9('sb.usedBy', { list: uses.slice(0, 3).map(d => `${d.kind.replace('_', ' ')} "${d.label}"`).join(', ') })}
                    {uses.length > 3 ? ` ${t9('sb.andMore', { n: uses.length - 3 })}` : ''}
                  </div>
                )}
              </div>
            )
          })}
          {usedTwice && <p role="alert" style={{ fontSize: 12, color: 'var(--danger, #c53030)', margin: 0 }}>
            {t9('sb.oneForOne')}</p>}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '10px 16px', borderTop: '1px solid var(--border)', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>{t9('cm.cancel')}</button>
          <button type="button" className="btn btn-sm" disabled={usedTwice} onClick={() => onForce(columnMap)}
            title={t9('sb.anywayTip')}>{t9('sb.anyway')}</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!allMapped || usedTwice}
            onClick={() => onMap(columnMap)}>{t9('sb.withNames')}</button>
        </div>
      </div>
    </div>
  )
}
