import { useEffect, useRef, useState } from 'react'
import { Bot, Check, X } from 'lucide-react'
import { reportsApi } from '../../services/api'
import type { AgentResult } from '../../services/api'
import { ResultGrid } from '../chat/ResultView'

/**
 * The page copilot: edit the OPEN dashboard page in plain language.
 *
 * A floating button in the builder (edit mode, edit rights only) opens this
 * panel. Each message goes to the copilot endpoint, which sees the page as
 * the server knows it — widgets, their configs, the dataset's columns — and
 * applies any requested edits before replying; the panel then asks the
 * builder to reload, so the canvas redraws the new state.
 *
 * It refuses NOTHING on this page (the complaint that shaped it: a config
 * change typed into the data chat came back "not answerable by SQL"). A page
 * command becomes applied edits; a DATA question is delegated server-side to
 * the same agent Ask AI uses, and the rows come back as a grid right here.
 *
 * Deliberately NOT ChatPane: that surface keeps its threads as the record of
 * answers. This one issues commands about the PAGE; the record of a command
 * is the page itself (plus the report's revision counter), so history lives
 * only in the panel for the session. Everything is component state and
 * async — nothing blocks the canvas.
 */
export interface CopilotChatProps {
  reportId: number
  pageId: number
  /** The widget selected on the canvas, so "the selected chart" and "it"
   *  mean what the user is looking at. */
  selectedWidgetId?: number | null
  /** Called after a reply whose actions changed the page, with what the
   *  server reports about the change (the version to restore to undo it). */
  onApplied: (change?: { beforeVersionId: number | null; summary: string | null }) => void | Promise<void>
}

interface Turn {
  id: number
  role: 'user' | 'assistant'
  text: string
  kind?: 'error'
  /** Human-readable summary of the edits this reply applied. */
  applied?: string[]
  /** Rows, when the message was a data question the agent answered. */
  results?: AgentResult[]
}

let nextId = 1

/** How many panel turns ride along with the next message, so "make it blue"
 *  can lean on what was just discussed without the prompt growing unbounded. */
const HISTORY_TURNS = 6

const APPLIED_VERB: Record<string, string> = {
  create: 'Added', update: 'Updated', delete: 'Removed',
  add_calculated_column: 'Added formula',
}

export default function CopilotChat({ reportId, pageId, selectedWidgetId, onApplied }: CopilotChatProps) {
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  // New content scrolls into view; the canvas behind never moves. Optional
  // call: jsdom elements have no scrollTo, and a missing scroll is cosmetic.
  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight })
  }, [turns, open])

  const send = async () => {
    const message = input.trim()
    if (!message || busy) return
    setInput('')
    setBusy(true)
    const history = turns
      .filter(t => t.kind !== 'error')
      .slice(-HISTORY_TURNS)
      .map(t => ({ role: t.role, content: t.text }))
    setTurns(t => [...t, { id: nextId++, role: 'user', text: message }])
    try {
      const got = await reportsApi.copilot(reportId, pageId,
        { message, history, selected_widget_id: selectedWidgetId ?? null })
      const applied = got.applied.map(a =>
        `${APPLIED_VERB[a.op] ?? a.op} ${a.title ?? `widget ${a.widget_id ?? ''}`}`.trim())
      setTurns(t => [...t, {
        id: nextId++, role: 'assistant',
        text: [got.reply, ...(got.notes ?? [])].filter(Boolean).join('\n'),
        applied, results: got.results ?? [],
      }])
      if (got.applied.length > 0) await onApplied({ beforeVersionId: got.before_version_id ?? null, summary: got.summary ?? null })
    } catch (e) {
      // A permission refusal is not a network problem; say which it was.
      const status = (e as { response?: { status?: number } })?.response?.status
      setTurns(t => [...t, {
        id: nextId++, role: 'assistant', kind: 'error',
        text: status === 403
          ? 'You do not have edit rights on this page.'
          : 'Could not reach the copilot. The page was not changed.',
      }])
    } finally {
      setBusy(false)
    }
  }

  // Float over the CANVAS, not over the settings panel: pinned to the window
  // corner, the button covered that panel's own bottom controls (its Send and
  // Apply buttons). The panel is resizable and collapsible, so follow its width.
  const endOffset = useEndPanelWidth('builder-right')

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} aria-label="Page copilot" title="Page copilot"
          style={{ position: 'fixed', insetInlineEnd: 24 + endOffset, bottom: 24, zIndex: 1000,
            width: 48, height: 48, borderRadius: '50%', border: 'none', cursor: 'pointer',
            background: 'var(--accent)', color: 'var(--mc-accent-fg)', display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 6px 20px rgb(15 23 42 / .25)' }}>
          <Bot size={22} aria-hidden />
        </button>
      )}

      {open && (
        <div role="dialog" aria-label="Page copilot"
          style={{ position: 'fixed', insetInlineEnd: 24 + endOffset, bottom: 24, zIndex: 1000,
            width: 360, maxWidth: 'calc(100vw - 48px)', height: 460,
            maxHeight: 'calc(100vh - 96px)', display: 'flex', flexDirection: 'column',
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 12, boxShadow: '0 12px 40px rgb(15 23 42 / .3)', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
            borderBottom: '1px solid var(--border)', background: 'var(--surface2)' }}>
            <Bot size={16} aria-hidden style={{ color: 'var(--accent)' }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700 }}>Page copilot</div>
              <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>
                Ask about this page, or tell it what to add or change.
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close copilot"
              style={{ background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--muted)', padding: 4, display: 'inline-flex' }}>
              <X size={15} aria-hidden />
            </button>
          </div>

          <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 10,
            display: 'flex', flexDirection: 'column', gap: 8 }}>
            {turns.length === 0 && (
              <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>
                Try: “add a bar chart of revenue by region”, “set the revenue
                chart’s auto-reload to 60 seconds”, “remove the table”, or a
                data question like “total revenue by region”.
              </p>
            )}
            {turns.map(t => (
              <div key={t.id} style={{
                alignSelf: t.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '90%',
                borderRadius: 10, padding: '7px 10px', fontSize: 12.5, whiteSpace: 'pre-wrap',
                ...(t.role === 'user'
                  ? { background: 'var(--accent)', color: 'var(--mc-accent-fg)' }
                  : t.kind === 'error'
                    ? { background: '#fdecec', border: '1px solid #f0acac', color: '#a4231f' }
                    : { background: 'var(--surface2)', color: 'var(--text)' }),
              }}>
                {t.text}
                {t.results && t.results.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    {t.results.map((r, i) => <ResultGrid key={i} result={r} />)}
                  </div>
                )}
                {t.applied && t.applied.length > 0 && (
                  <ul style={{ listStyle: 'none', margin: '6px 0 0', padding: 0,
                    display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {t.applied.map((a, i) => (
                      <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 5,
                        fontSize: 11.5, color: 'var(--success, #16a34a)' }}>
                        <Check size={12} aria-hidden /> {a}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            {busy && (
              <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>Working…</span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 6, padding: 10, borderTop: '1px solid var(--border)' }}>
            <input value={input} disabled={busy}
              placeholder="Tell the copilot what to do…"
              aria-label="Copilot message"
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void send() }}
              style={{ flex: 1, padding: '7px 9px', fontSize: 12.5,
                border: '1px solid var(--border)', borderRadius: 6,
                background: 'var(--surface)', color: 'var(--text)' }} />
            <button onClick={() => void send()} disabled={busy}
              style={{ padding: '7px 12px', fontSize: 12.5, borderRadius: 6, border: 'none',
                background: busy ? 'var(--muted)' : 'var(--accent)', color: 'var(--mc-accent-fg)',
                cursor: busy ? 'default' : 'pointer' }}>
              Send
            </button>
          </div>
        </div>
      )}
    </>
  )
}

function useEndPanelWidth(sideId: string): number {
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = document.querySelector<HTMLElement>(`[data-side="${sideId}"]`)
    if (!el || typeof ResizeObserver === 'undefined') return
    const measure = () => setW(Math.round(el.getBoundingClientRect().width))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [sideId])
  return w
}
