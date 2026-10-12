import { useContext, useEffect, useRef, useState, type PointerEvent as RPointerEvent } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { useT } from '../../i18n'
import AiMascot from './AiMascot'
import './askFab.css'

/**
 * The floating Ask AI button on a dashboard (autopilot step 6, design
 * `AI Button Redesign.html`): the mascot on a round accent button that opens
 * into an "Ask AI" pill on hover or focus, with the shortcut in a tooltip. At
 * rest it breathes and the mascot blinks; while the page scrolls it shrinks
 * and fades so it is out of the way. It can be dragged to any corner of the
 * canvas, and the corner is remembered for this user in this browser.
 *
 * It opens what it always opened (the page's own AI panel, beside the
 * dashboard, never over it). The page hides it in Present and in Edit, where
 * the copilot is the page's own. Ctrl+/ is handled by the page.
 *
 * Left out: the design's "new insight" badge. Knowing whether a dataset has
 * new insights means running a scan (backend row: an insight count).
 */
export type Corner = 'be' | 'bs' | 'te' | 'ts'   // bottom/top, inline end/start
const corners: Corner[] = ['be', 'bs', 'te', 'ts']

export default function AskFab({ onOpen, alive }: { onOpen: () => void; alive: boolean }) {
  const t = useT()
  const userId = useContext(AuthContext)?.user?.id ?? 'anon'
  const key = `datalytics.askFab.corner.${userId}`
  const [corner, setCorner] = useState<Corner>(() => {
    try { const v = localStorage.getItem(key) as Corner | null; return v && corners.includes(v) ? v : 'be' } catch { return 'be' }
  })
  const [quiet, setQuiet] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; moved: boolean; id: number } | null>(null)
  // The click a browser sends after a drag is not a press.
  const dragged = useRef(false)
  const [offset, setOffset] = useState<{ x: number; y: number } | null>(null)

  // Quiet while anything under it scrolls; back after a moment of stillness.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const onScroll = (e: Event) => {
      const box = wrap.current?.parentElement
      if (!box || !(e.target instanceof Node) || !box.contains(e.target)) return
      setQuiet(true)
      clearTimeout(timer)
      timer = setTimeout(() => setQuiet(false), 600)
    }
    document.addEventListener('scroll', onScroll, { capture: true, passive: true })
    return () => { document.removeEventListener('scroll', onScroll, { capture: true }); clearTimeout(timer) }
  }, [])

  const down = (e: RPointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    drag.current = { x: e.clientX, y: e.clientY, moved: false, id: e.pointerId }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const move = (e: RPointerEvent<HTMLButtonElement>) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < 6) return
    d.moved = true
    setOffset({ x: dx, y: dy })
  }
  const up = (e: RPointerEvent<HTMLButtonElement>) => {
    const d = drag.current
    drag.current = null
    e.currentTarget.releasePointerCapture?.(e.pointerId)
    if (!d?.moved) return
    dragged.current = true
    // Dropped: the nearest corner of the canvas, in reading terms.
    const box = wrap.current?.parentElement?.getBoundingClientRect()
    setOffset(null)
    if (!box) return
    const rtl = getComputedStyle(wrap.current!).direction === 'rtl'
    const right = e.clientX > box.left + box.width / 2
    const bottom = e.clientY > box.top + box.height / 2
    const next = `${bottom ? 'b' : 't'}${right !== rtl ? 'e' : 's'}` as Corner
    setCorner(next)
    try { localStorage.setItem(key, next) } catch { /* a convenience */ }
  }
  const click = () => { if (dragged.current) { dragged.current = false; return } onOpen() }

  return (
    <div ref={wrap} className={`dl-fab dl-fab--${corner}${quiet ? ' is-quiet' : ''}${offset ? ' is-drag' : ''}`}
      style={offset ? { transform: `translate(${offset.x}px, ${offset.y}px)` } : undefined}>
      <span className="dl-fab__tip" role="tooltip" id="dl-fab-tip">
        {t('fab.tip')} <kbd dir="ltr">Ctrl</kbd> <kbd dir="ltr">/</kbd>
      </span>
      <button type="button" className="dl-fab__b" onClick={click} onPointerDown={down} onPointerMove={move} onPointerUp={up}
        aria-label={t('fab.tip')} aria-describedby="dl-fab-tip" aria-keyshortcuts="Control+/" data-testid="view-ai-open">
        <span className="dl-fab__ic" aria-hidden><AiMascot size={36} alive={alive} /></span>
        <span className="dl-fab__l">{t('nav.askAi')}</span>
      </button>
    </div>
  )
}
