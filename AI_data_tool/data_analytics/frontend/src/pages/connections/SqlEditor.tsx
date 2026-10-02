/**
 * The Browse SQL editor (4.3): a bigger textarea with schema autocomplete.
 * Suggestions appear for the word at the caret; ↑/↓ move, Tab or Enter
 * accept, Esc closes. Ctrl/⌘+Enter runs the query.
 */
import { useMemo, useRef, useState } from 'react'
import { applySuggestion, mentionedTables, suggest } from '../../lib/sqlSuggest'

export default function SqlEditor({ value, onChange, onRun, tables, columnsByTable, onNeedColumns, placeholder, label }: {
  value: string
  onChange: (v: string) => void
  onRun?: () => void
  tables: string[]
  columnsByTable: Record<string, string[]>
  /** Asked for a table's columns once the statement mentions it. */
  onNeedColumns?: (table: string) => void
  placeholder?: string
  label: string
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [caret, setCaret] = useState(0)
  const [active, setActive] = useState(0)
  const [closed, setClosed] = useState(false)
  const items = useMemo(() => (closed ? [] : suggest(value, caret, tables, columnsByTable)),
    [value, caret, tables, columnsByTable, closed])

  const accept = (i: number) => {
    const it = items[i]
    if (!it) return
    const next = applySuggestion(value, caret, it.insert)
    onChange(next.text)
    setCaret(next.caret)
    setClosed(true)
    requestAnimationFrame(() => {
      ref.current?.focus()
      ref.current?.setSelectionRange(next.caret, next.caret)
    })
  }

  const changed = (text: string, pos: number) => {
    onChange(text)
    setCaret(pos)
    setActive(0)
    setClosed(false)
    if (onNeedColumns) for (const t of mentionedTables(text, tables)) if (!columnsByTable[t]) onNeedColumns(t)
  }

  return (
    <div style={{ position: 'relative' }}>
      <textarea ref={ref} aria-label={label} value={value} placeholder={placeholder} rows={7} spellCheck={false}
        dir="ltr" aria-autocomplete="list" aria-expanded={items.length > 0}
        onChange={e => changed(e.target.value, e.target.selectionStart ?? e.target.value.length)}
        onClick={e => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? 0)}
        onKeyUp={e => {
          if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) setCaret((e.target as HTMLTextAreaElement).selectionStart ?? 0)
        }}
        onKeyDown={e => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); onRun?.(); return }
          // Escape with no suggestion open used to reach the dialog and close
          // it, throwing the query away (found in the Chrome re-test). The first
          // Escape now only leaves the editor; a second one closes the dialog.
          if (e.key === 'Escape' && !items.length && value.trim()) {
            e.stopPropagation(); e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); return
          }
          if (!items.length) return
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => (a + 1) % items.length) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => (a - 1 + items.length) % items.length) }
          else if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); accept(active) }
          else if (e.key === 'Escape') { e.stopPropagation(); setClosed(true) }
        }}
        style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: 12.5, lineHeight: 1.5, padding: '8px 10px',
          background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, minHeight: 130,
          color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box' }} />
      {items.length > 0 && (
        <ul role="listbox" aria-label="Suggestions"
          style={{ position: 'absolute', insetInlineStart: 8, top: '100%', zIndex: 5, margin: 0, padding: 4,
            listStyle: 'none', minWidth: 220, background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,.18)', fontSize: 12 }}>
          {items.map((it, i) => (
            <li key={it.label} role="option" aria-selected={i === active}
              onMouseDown={e => { e.preventDefault(); accept(i) }}
              style={{ padding: '4px 8px', borderRadius: 5, cursor: 'pointer', display: 'flex', gap: 8,
                background: i === active ? 'var(--accent-soft, var(--surface2))' : 'transparent' }}>
              <span style={{ fontFamily: 'var(--mono)' }}>{it.label}</span>
              <span style={{ marginInlineStart: 'auto', color: 'var(--muted)', fontSize: 10.5 }}>{it.kind}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
