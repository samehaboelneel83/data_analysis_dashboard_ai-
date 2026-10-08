import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent } from 'react'
import { useAiOffline } from '../../pages/ask/useAiOffline'
import { ArrowUp, ArrowUpRight, BookOpen, Check, Lightbulb, Minus, MoreHorizontal, PencilLine,
  RotateCcw, Sparkles, TrendingUp, X } from 'lucide-react'
import { insightsApi, reportsApi } from '../../services/api'
import type { AgentResult, AnswerEvidence } from '../../services/api'
import ResultView, { focusFor, type EvidenceFocus } from '../chat/ResultView'
import AnswerText from '../chat/AnswerText'
import AiMascot from '../ai/AiMascot'
import { useT } from '../../i18n'
import { aiLimitMessage } from '../../lib/aiLimit'
import { localDigits } from '../../lib/arabicFormats'
import './copilot.css'

/**
 * Ask AI on a dashboard page: edit the OPEN page in plain language, or ask
 * about its data.
 *
 * A floating mascot button in the builder (edit mode, edit rights only)
 * opens this panel. Each message goes to the copilot endpoint, which sees the
 * page as the server knows it — widgets, their configs, the dataset's
 * columns — and applies any requested edits before replying; the panel then
 * asks the builder to reload, so the canvas redraws the new state.
 *
 * It refuses NOTHING on this page (the complaint that shaped it: a config
 * change typed into the data chat came back "not answerable by SQL"). A page
 * command becomes applied edits; a DATA question is delegated server-side to
 * the same agent Ask AI uses, and the rows come back right here.
 *
 * Deliberately NOT ChatPane: that surface keeps its threads as the record of
 * answers. This one issues commands about the PAGE; the record of a command
 * is the page itself (plus the report's revision counter), so history lives
 * only in the panel for the session.
 *
 * The button: breathes and blinks at rest; opens into an "Ask AI" pill on
 * hover/focus (tooltip names Ctrl+/); turns into a close button while the
 * panel is open; shrinks and fades while the canvas scrolls; can be dragged
 * to any corner (remembered; Alt+arrows from the keyboard); mirrors in RTL;
 * hidden while presenting. A dot marks a finding from the dataset's insight
 * scan that this person hasn't seen yet -- never a made-up one.
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
  /** Context for the header, greeting and suggestions. All optional. */
  reportName?: string
  pageName?: string
  widgetCount?: number
  selectedWidgetTitle?: string | null
  /** The report's dataset: its insight scan feeds the badge and card. */
  datasetId?: number | null
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
  /** The reply's numbers, traced to those rows (E11). */
  evidence?: AnswerEvidence | null
}

interface Insight { key: string; title: string; detail: string }

let nextId = 1

/** How many panel turns ride along with the next message, so "make it blue"
 *  can lean on what was just discussed without the prompt growing unbounded. */
const HISTORY_TURNS = 6

type Corner = 'bottom-end' | 'bottom-start' | 'top-end' | 'top-start'
const CORNER_KEY = 'datalytics.askai.corner'
const SEEN_KEY = 'datalytics.askai.seenInsights'
const INSIGHT_CACHE = 'datalytics.askai.insight.'

const readCorner = (): Corner => {
  try {
    const v = localStorage.getItem(CORNER_KEY)
    return v === 'bottom-start' || v === 'top-end' || v === 'top-start' ? v : 'bottom-end'
  } catch { return 'bottom-end' }
}
const readSeen = (): string[] => {
  try { const v = JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'); return Array.isArray(v) ? v : [] } catch { return [] }
}
const isRtl = () => typeof document !== 'undefined' && document.documentElement.dir === 'rtl'

export default function CopilotChat({
  reportId, pageId, selectedWidgetId, onApplied,
  reportName, pageName, widgetCount, selectedWidgetTitle, datasetId,
}: CopilotChatProps) {
  const t = useT()
  const [open, setOpen] = useState(false)
  // 7e5: the top bar's model light, as Ask AI reads it (4b). While it is
  // down, new requests are paused and the panel says why in one line.
  const { offline } = useAiOffline()
  const [turns, setTurns] = useState<Turn[]>([])
  // The number of a reply whose source the reader asked to see (E11).
  const [evidenceFocus, setEvidenceFocus] = useState<{ turn: number; at: EvidenceFocus } | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [corner, setCorner] = useState<Corner>(readCorner)
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null)
  const [scrolling, setScrolling] = useState(false)
  const [presenting, setPresenting] = useState(
    () => typeof document !== 'undefined' && document.documentElement.dataset.presenting === '1')
  const [insight, setInsight] = useState<Insight | null>(null)
  const [seen, setSeen] = useState<string[]>(readSeen)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const dragStart = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const suppressClick = useRef(false)

  const toggle = useCallback(() => { setOpen(o => !o); setMenuOpen(false) }, [])

  // Escape closes; Ctrl+/ (Cmd+/) toggles from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) { setOpen(false); btnRef.current?.focus(); return }
      if ((e.ctrlKey || e.metaKey) && e.key === '/') { e.preventDefault(); toggle() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, toggle])

  // Opening puts the cursor in the question box.
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  // New content scrolls into view; the canvas behind never moves. Optional
  // call: jsdom elements have no scrollTo, and a missing scroll is cosmetic.
  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight })
  }, [turns, open, busy])

  // Get out of the way while the canvas scrolls: shrink and fade, then come
  // back shortly after the scrolling stops. Scrolls inside the panel don't count.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const onScroll = (e: Event) => {
      if (panelRef.current && e.target instanceof Node && panelRef.current.contains(e.target)) return
      setScrolling(true)
      clearTimeout(timer)
      timer = setTimeout(() => setScrolling(false), 700)
    }
    document.addEventListener('scroll', onScroll, true)
    return () => { document.removeEventListener('scroll', onScroll, true); clearTimeout(timer) }
  }, [])

  // Present mode hides it (the builder stamps <html data-presenting="1"> and
  // announces the switch).
  useEffect(() => {
    const on = (e: Event) => setPresenting(!!(e as CustomEvent).detail)
    window.addEventListener('datalytics:present', on)
    return () => window.removeEventListener('datalytics:present', on)
  }, [])

  // One real finding from the dataset's insight scan, if there is one. The
  // scan is shared with the pin cards (runShared) and cached for the browser
  // session, so opening the builder doesn't start a new scan every time.
  useEffect(() => {
    if (datasetId == null) return
    let alive = true
    const cacheKey = INSIGHT_CACHE + datasetId
    try {
      const cached = sessionStorage.getItem(cacheKey)
      if (cached) { setInsight(JSON.parse(cached)); return () => { alive = false } }
    } catch { /* no cache */ }
    const timer = setTimeout(() => {
      if (typeof insightsApi?.runShared !== 'function') return
      insightsApi.runShared(datasetId)
        .then(r => {
          const top = [...(r?.findings ?? [])]
            .filter(f => f.novelty !== 'unchanged')
            .sort((a, b) => b.score - a.score)[0]
          const found = top
            ? { key: `${datasetId}:${top.kind}:${top.columns.join(',')}`, title: top.title, detail: top.detail }
            : null
          try { sessionStorage.setItem(cacheKey, JSON.stringify(found)) } catch { /* ok */ }
          if (alive) setInsight(found)
        })
        .catch(() => { /* no insight is fine: the badge simply doesn't show */ })
    }, 2500)
    return () => { alive = false; clearTimeout(timer) }
  }, [datasetId])

  const badge = !!insight && !open && !seen.includes(insight.key)
  useEffect(() => {
    // Seeing the card in the open panel counts as having seen the insight.
    if (open && insight && !seen.includes(insight.key)) {
      const next = [...seen, insight.key].slice(-50)
      setSeen(next)
      try { localStorage.setItem(SEEN_KEY, JSON.stringify(next)) } catch { /* ok */ }
    }
  }, [open, insight, seen])

  const send = async (text?: string) => {
    const message = (text ?? input).trim()
    if (!message || busy) return
    if (text === undefined) setInput('')
    setBusy(true)
    const history = turns
      .filter(x => x.kind !== 'error')
      .slice(-HISTORY_TURNS)
      .map(x => ({ role: x.role, content: x.text }))
    setTurns(x => [...x, { id: nextId++, role: 'user', text: message }])
    try {
      const got = await reportsApi.copilot(reportId, pageId,
        { message, history, selected_widget_id: selectedWidgetId ?? null })
      const applied = got.applied.map(a =>
        `${appliedVerb(a.op, t)} ${a.title ?? `widget ${a.widget_id ?? ''}`}`.trim())
      setTurns(x => [...x, {
        id: nextId++, role: 'assistant',
        text: [got.reply, ...(got.notes ?? [])].filter(Boolean).join('\n'),
        applied, results: got.results ?? [],
        // Traced against the reply alone: notes are the copilot's own.
        evidence: got.notes?.length ? null : got.evidence ?? null,
      }])
      if (got.applied.length > 0) await onApplied({ beforeVersionId: got.before_version_id ?? null, summary: got.summary ?? null })
    } catch (e) {
      // A permission refusal is not a network problem; say which it was.
      const status = (e as { response?: { status?: number } })?.response?.status
      setTurns(x => [...x, {
        id: nextId++, role: 'assistant', kind: 'error',
        text: status === 403 ? t('copilot.err.forbidden')
          : aiLimitMessage(e, t) ?? t('copilot.err.unreachable'),
      }])
    } finally {
      setBusy(false)
    }
  }

  // ── Drag to a corner ──────────────────────────────────────────────────────
  const saveCorner = (c: Corner) => {
    setCorner(c)
    try { localStorage.setItem(CORNER_KEY, c) } catch { /* ok */ }
  }
  const onPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    dragStart.current = { x: e.clientX, y: e.clientY, moved: false }
  }
  const onPointerMove = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const s = dragStart.current
    if (!s) return
    if (!s.moved && Math.hypot(e.clientX - s.x, e.clientY - s.y) < 6) return
    if (!s.moved) {
      s.moved = true
      suppressClick.current = true
      e.currentTarget.setPointerCapture?.(e.pointerId)
      setOpen(false)
    }
    setDrag({ x: e.clientX, y: e.clientY })
  }
  const onPointerUp = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const s = dragStart.current
    dragStart.current = null
    if (!s?.moved) return
    const right = e.clientX > window.innerWidth / 2
    const end = isRtl() ? !right : right
    saveCorner(`${e.clientY > window.innerHeight / 2 ? 'bottom' : 'top'}-${end ? 'end' : 'start'}`)
    setDrag(null)
  }
  // A drag ends in pointerup; the click that follows must not toggle the panel.
  const onClick = () => {
    if (suppressClick.current) { suppressClick.current = false; return }
    toggle()
  }
  // Keyboard users can move it too: Alt+arrows pick the corner.
  const onBtnKey = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!e.altKey) return
    const rtl = isRtl()
    const toStart = (c: Corner) => c.replace('end', 'start') as Corner
    const toEnd = (c: Corner) => c.replace('start', 'end') as Corner
    const map: Record<string, (c: Corner) => Corner> = {
      ArrowUp: c => c.replace('bottom', 'top') as Corner,
      ArrowDown: c => c.replace('top', 'bottom') as Corner,
      ArrowLeft: rtl ? toEnd : toStart,
      ArrowRight: rtl ? toStart : toEnd,
    }
    const f = map[e.key]
    if (!f) return
    e.preventDefault()
    saveCorner(f(corner))
  }

  // Float over the CANVAS, never over the panels beside it (QA3 B1).
  const inset = useCanvasInsets()

  if (presenting) return null

  const [vert, horiz] = corner.split('-') as ['top' | 'bottom', 'start' | 'end']
  const pos: React.CSSProperties = drag
    ? { left: drag.x - 28, top: drag.y - 28 }
    : {
        [vert]: vert === 'bottom' ? 'var(--dl-askai-bottom)' : 'var(--dl-askai-top)',
        [horiz === 'end' ? 'insetInlineEnd' : 'insetInlineStart']: (horiz === 'end' ? inset.end : inset.start) + 24,
      }

  const n = widgetCount ?? 0
  const page = pageName || t('copilot.thisPage')
  const suggestions: { icon: typeof BookOpen; text: string; fill?: boolean }[] = [
    { icon: BookOpen, text: t('copilot.sug.explain') },
    selectedWidgetTitle
      ? { icon: Sparkles, text: t('copilot.sug.summarize', { name: selectedWidgetTitle }) }
      : { icon: TrendingUp, text: t('copilot.sug.stands') },
    { icon: Sparkles, text: t('copilot.sug.improve') },
    { icon: PencilLine, text: t('copilot.sug.addChart'), fill: true },
  ]

  const cls = ['dl-askai', `dl-askai--${vert}`, `dl-askai--${horiz}`]
  if (open) cls.push('is-open')
  if (scrolling && !open) cls.push('is-shy')
  if (drag) cls.push('is-dragging')

  return (
    <div className={cls.join(' ')} style={pos}>
      {open && (
        <div ref={panelRef} role="dialog" aria-label={t('copilot.title')} className="dl-askai__panel">
          <header className="dl-askai__head">
            <span className="dl-askai__avatar" aria-hidden><AiMascot size={22} /></span>
            <div className="dl-askai__head-text">
              <div className="dl-askai__title">{t('copilot.title')}</div>
              {(reportName || pageName) && (
                <div className="dl-askai__context" dir="auto"
                  title={[reportName, pageName].filter(Boolean).join(' · ')}>
                  {[reportName, pageName].filter(Boolean).join(' · ')}
                </div>
              )}
            </div>
            <div className="dl-askai__menu-wrap">
              <button type="button" className="dl-askai__icon" aria-label={t('copilot.more')} title={t('copilot.more')}
                aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(o => !o)}>
                <MoreHorizontal size={16} aria-hidden />
              </button>
              {menuOpen && (
                <div role="menu" className="dl-askai__menu">
                  <button type="button" role="menuitem" disabled={turns.length === 0 || busy}
                    onClick={() => { setTurns([]); setMenuOpen(false); inputRef.current?.focus() }}>
                    <RotateCcw size={14} aria-hidden /> {t('copilot.newChat')}
                  </button>
                  <button type="button" role="menuitem"
                    onClick={() => {
                      setCorner('bottom-end'); setMenuOpen(false)
                      try { localStorage.removeItem(CORNER_KEY) } catch { /* ok */ }
                    }}>
                    <ArrowUpRight size={14} aria-hidden className="dl-askai__flip" /> {t('copilot.resetCorner')}
                  </button>
                </div>
              )}
            </div>
            <button type="button" className="dl-askai__icon" aria-label={t('copilot.minimize')} title={t('copilot.minimize')}
              onClick={() => { setOpen(false); btnRef.current?.focus() }}>
              <Minus size={16} aria-hidden />
            </button>
            <button type="button" className="dl-askai__icon" aria-label={t('copilot.endChat')} title={t('copilot.endChat')}
              onClick={() => { setOpen(false); setTurns([]); btnRef.current?.focus() }}>
              <X size={16} aria-hidden />
            </button>
          </header>

          <div ref={listRef} className="dl-askai__body">
            {turns.length === 0 && (
              <div className="dl-askai__hello">
                <p className="dl-askai__hello-title">{t('copilot.hello', { page })}</p>
                <p className="dl-askai__hello-sub">
                  {n > 0 ? t('copilot.helloSub', { n: localDigits(String(n)) }) : t('copilot.helloSubEmpty')}
                </p>
                {insight && (
                  <div className="dl-askai__insight">
                    <span className="dl-askai__insight-icon" aria-hidden><Lightbulb size={15} /></span>
                    <div className="dl-askai__insight-body">
                      <p className="dl-askai__insight-title">{t('copilot.insight')}</p>
                      <p className="dl-askai__insight-text" dir="auto">
                        {insight.title}{insight.detail ? ` — ${insight.detail}` : ''}
                      </p>
                      <button type="button" className="dl-askai__insight-more" disabled={busy || offline}
                        onClick={() => void send(t('copilot.tellMore', { title: insight.title }))}>
                        {t('copilot.tellMoreBtn')}
                      </button>
                    </div>
                  </div>
                )}
                <p className="dl-askai__sug-label">{t('copilot.suggested')}</p>
                <ul className="dl-askai__sug">
                  {suggestions.map(s => (
                    <li key={s.text}>
                      <button type="button" disabled={busy || offline}
                        onClick={() => {
                          if (s.fill) { setInput(s.text + ' '); inputRef.current?.focus() }
                          else void send(s.text)
                        }}>
                        <s.icon size={15} aria-hidden className="dl-askai__sug-icon" />
                        <span dir="auto">{s.text}</span>
                        {s.fill
                          ? <PencilLine size={13} aria-hidden className="dl-askai__sug-go" />
                          : <ArrowUpRight size={13} aria-hidden className="dl-askai__sug-go dl-askai__flip" />}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {turns.map(x => x.role === 'user' ? (
              <div key={x.id} className="dl-askai__msg dl-askai__msg--user" dir="auto">{x.text}</div>
            ) : (
              <div key={x.id} className={`dl-askai__msg dl-askai__msg--ai${x.kind === 'error' ? ' is-error' : ''}`}>
                <span className="dl-askai__avatar dl-askai__avatar--sm" aria-hidden><AiMascot size={16} /></span>
                <div className="dl-askai__msg-body">
                  {x.evidence && x.results?.length ? (
                    <div className="dl-askai__msg-text">
                      <AnswerText text={x.text} evidence={x.evidence}
                        onShow={c => setEvidenceFocus(f => {
                          const at = focusFor(c, f?.at)
                          return at ? { turn: x.id, at } : f
                        })} />
                    </div>
                  ) : (
                    <div className="dl-askai__msg-text" dir="auto">{x.text}</div>
                  )}
                  {x.results && x.results.length > 0 && (
                    <div className="dl-askai__result">
                      <ResultView results={x.results}
                        focus={evidenceFocus?.turn === x.id ? evidenceFocus.at : null} />
                    </div>
                  )}
                  {x.applied && x.applied.length > 0 && (
                    <ul className="dl-askai__applied">
                      {x.applied.map((a, i) => (
                        <li key={i}><Check size={12} aria-hidden /> {a}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            ))}

            {busy && (
              <div className="dl-askai__msg dl-askai__msg--ai dl-askai__thinking" role="status" aria-live="polite">
                <span className="dl-askai__avatar dl-askai__avatar--sm" aria-hidden><AiMascot size={16} /></span>
                <div className="dl-askai__msg-body">
                  <strong className="dl-askai__thinking-title">{t('copilot.thinking')}</strong>
                  <span className="dl-askai__dots" aria-hidden><i /><i /><i /></span>
                  <p className="dl-askai__reading">
                    {n > 0 ? t('copilot.reading', { n: localDigits(String(n)), page }) : t('copilot.readingPage', { page })}
                  </p>
                  <span className="dl-askai__skel" aria-hidden><i /><i /><i /></span>
                </div>
              </div>
            )}
          </div>

          <div className="dl-askai__composer">
            {offline && <p role="status" className="dl-chat__note dl-chat__note--error dl-chat__offline" data-testid="copilot-offline">{t('off.title')}</p>}
            <div className="dl-askai__box">
              <textarea ref={inputRef} rows={1} value={input} disabled={busy || offline}
                placeholder={offline ? t('off.composer') : t('copilot.placeholder')}
                aria-label={t('copilot.inputLabel')}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send() }
                }} />
              <button type="button" className="dl-askai__send" onClick={() => void send()} disabled={busy || offline}
                aria-label={t('copilot.send')} title={t('copilot.send')}>
                <ArrowUp size={16} aria-hidden />
              </button>
            </div>
            <p className="dl-askai__hint" aria-hidden>
              <kbd>Enter</kbd> {t('copilot.hintSend')} · <kbd>Shift</kbd>+<kbd>Enter</kbd> {t('copilot.hintLine')}
            </p>
          </div>
        </div>
      )}

      <div className="dl-askai__anchor">
        {!open && !drag && (
          <span className="dl-askai__tip" role="tooltip" id="dl-askai-tip">
            {t('copilot.tooltip')} <kbd>Ctrl</kbd> <kbd>/</kbd>
          </span>
        )}
        <button ref={btnRef} type="button" className={`dl-askai__btn${badge ? ' has-badge' : ''}`}
          aria-label={open ? t('copilot.hide') : t('copilot.open')}
          aria-expanded={open} aria-describedby={open ? undefined : 'dl-askai-tip'}
          aria-keyshortcuts="Control+/"
          onClick={onClick} onKeyDown={onBtnKey}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
          onPointerCancel={() => { dragStart.current = null; setDrag(null) }}>
          <span className="dl-askai__label">{t('copilot.title')}</span>
          <span className="dl-askai__face" aria-hidden>
            {open ? <X size={22} /> : <AiMascot size={30} alive />}
          </span>
          {badge && <span className="dl-askai__badge" aria-hidden />}
          {badge && <span className="dl-sr-only">{t('copilot.badge')}</span>}
        </button>
      </div>
    </div>
  )
}

function appliedVerb(op: string, t: ReturnType<typeof useT>): string {
  switch (op) {
    case 'create': return t('copilot.applied.create')
    case 'update': return t('copilot.applied.update')
    case 'delete': return t('copilot.applied.delete')
    case 'add_calculated_column': return t('copilot.applied.formula')
    default: return op
  }
}

/** QA3 B1: how far the canvas column's edges sit from the window's edges, so the button floats inside the canvas whatever is beside it: the
 *  settings panel, the pinned Properties next to it, and the icon rail (v1
 *  measured only the settings panel, so the button sat on its section
 *  headers, the Comments box and "Add schedule"). Follows resizes and RTL. */
function useCanvasInsets(): { start: number; end: number } {
  const [w, setW] = useState({ start: 0, end: 0 })
  useEffect(() => {
    const el = document.querySelector<HTMLElement>('[data-canvas-scroll]')
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      const rtl = getComputedStyle(document.documentElement).direction === 'rtl'
      const left = Math.max(0, Math.round(r.left)), right = Math.max(0, Math.round(window.innerWidth - r.right))
      setW(rtl ? { start: right, end: left } : { start: left, end: right })
    }
    measure()
    window.addEventListener('resize', measure)
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    ro?.observe(el)
    return () => { window.removeEventListener('resize', measure); ro?.disconnect() }
  }, [])
  return w
}
