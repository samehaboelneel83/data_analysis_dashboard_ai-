import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

const STORAGE_KEY = 'datalytics.builderPanels'
const WIDTH_KEY = 'datalytics.builderPanelWidths'

/** Width of the rail a collapsed panel leaves behind: enough to hit the reopen
 *  control and nothing more. A panel that collapsed to zero would be unreachable. */
export const RAIL_W = 26

/** Floor for a resized panel. Below this the panel's own controls start clipping,
 *  and an author who wants less than this wants the panel collapsed instead. */
export const MIN_PANEL_W = 180

/** Ceiling, so a dragged panel can never squeeze the canvas out of existence. */
export const MAX_PANEL_W = 520

/** Keyboard step for the resize separator, matching the grid gap so arrow-key
 *  resizing lands on the same rhythm a mouse drag does. */
const KEY_STEP = 8

/** Read a stored map. Storage is shared with other tabs and can hold anything, so a
 *  parse failure degrades to "nothing remembered" rather than breaking the builder. */
function readMap<T>(key: string): Record<string, T> {
  try {
    const raw = localStorage.getItem(key)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function writeMap(key: string, id: string, value: boolean | number) {
  try {
    localStorage.setItem(key, JSON.stringify({ ...readMap(key), [id]: value }))
  } catch {
    // Storage full or blocked (private mode). Collapsing and resizing still work for
    // this session; only the memory across navigations is lost, which is not worth
    // failing a render over.
  }
}

const clampW = (w: number) => Math.min(MAX_PANEL_W, Math.max(MIN_PANEL_W, Math.round(w)))

interface Props {
  /** Stable key for the remembered open/closed state. */
  id: string
  /** Which edge the panel sits on -- decides which way the chevrons point. */
  side: 'left' | 'right'
  /** Expanded width in px. Collapsed width is always RAIL_W. */
  width: number
  /** Names the region for assistive tech and labels the reopen control. */
  title: string
  style?: React.CSSProperties
  children: React.ReactNode
  /** When this value changes, the content's scroll position resets to the top.
   *  Used by the right panel so switching the selected widget/page always shows
   *  its content from the top, instead of wherever the previous selection had
   *  scrolled to. */
  scrollResetKey?: string | number | null
  /** Each change re-opens a collapsed panel -- e.g. "Assign data" on a widget
   *  must land the author in its settings even if they had folded them away. */
  openSignal?: number
}

/**
 * A side panel the author can collapse to reclaim its width for the canvas.
 *
 * The builder's canvas is `flex: 1` between two fixed-width panels, so in edit mode
 * roughly 500px of every screen was permanently unavailable to it. Collapsing a panel
 * gives that width back to the canvas without unmounting anything the author might be
 * mid-edit in -- the children stay mounted and merely hidden, so an open dropdown or a
 * half-typed field survives a collapse.
 */
export default function CollapsibleSide({ id, side, width, title, style, children, scrollResetKey, openSignal }: Props) {
  const [open, setOpen] = useState(() => readMap<boolean>(STORAGE_KEY)[id] ?? true)
  useEffect(() => { if (openSignal) setOpen(true) }, [openSignal])
  const [panelW, setPanelW] = useState(() => {
    const saved = readMap<number>(WIDTH_KEY)[id]
    return typeof saved === 'number' && Number.isFinite(saved) ? clampW(saved) : width
  })
  const [dragging, setDragging] = useState(false)
  const shellRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollResetKey === undefined) return
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [scrollResetKey])

  const toggle = useCallback(() => {
    setOpen(prev => {
      writeMap(STORAGE_KEY, id, !prev)
      return !prev
    })
  }, [id])

  const commitWidth = useCallback((w: number) => {
    const next = clampW(w)
    setPanelW(next)
    writeMap(WIDTH_KEY, id, next)
  }, [id])

  // Resize follows the pointer against the panel's OUTER edge, so the width tracks the
  // cursor exactly rather than accumulating deltas -- a drag that leaves the window and
  // comes back therefore resumes correctly instead of jumping.
  useEffect(() => {
    if (!dragging) return
    const onMove = (e: PointerEvent) => {
      const rect = shellRef.current?.getBoundingClientRect()
      if (!rect) return
      setPanelW(clampW(side === 'right' ? rect.right - e.clientX : e.clientX - rect.left))
    }
    const onUp = () => {
      setDragging(false)
      setPanelW(w => { writeMap(WIDTH_KEY, id, w); return w })
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    // Suppress text selection for the duration of the drag; without it the pointer
    // sweeps a selection across the whole builder.
    const prevSelect = document.body.style.userSelect
    document.body.style.userSelect = 'none'
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.style.userSelect = prevSelect
    }
  }, [dragging, side, id])

  const onSeparatorKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Arrow keys widen away from the canvas and narrow toward it, matching the drag
    // direction for each edge, so the separator is usable without a pointer.
    const grow = side === 'right' ? 'ArrowLeft' : 'ArrowRight'
    const shrink = side === 'right' ? 'ArrowRight' : 'ArrowLeft'
    if (e.key === grow) { e.preventDefault(); commitWidth(panelW + KEY_STEP) }
    else if (e.key === shrink) { e.preventDefault(); commitWidth(panelW - KEY_STEP) }
    else if (e.key === 'Home') { e.preventDefault(); commitWidth(MIN_PANEL_W) }
    else if (e.key === 'End') { e.preventDefault(); commitWidth(MAX_PANEL_W) }
  }, [side, panelW, commitWidth])

  // Chevron points the way the panel will move: on the right edge, collapsing pushes
  // it right, so an open panel shows ">" and a collapsed rail shows "<".
  const pointsAway = side === 'right' ? open : !open
  const Chevron = pointsAway ? ChevronRight : ChevronLeft

  return (
    <div
      ref={shellRef}
      style={{
        width: open ? panelW : RAIL_W,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
        // No width transition mid-drag: an eased width lags the pointer and reads as lag.
        transition: dragging ? 'none' : 'width .14s ease',
        ...(open ? style : { background: 'var(--surface)', [side === 'right' ? 'borderInlineStart' : 'borderInlineEnd']: '1px solid var(--border)' }),
      }}
    >
      {open && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={`Resize ${title}`}
          aria-valuenow={panelW}
          aria-valuemin={MIN_PANEL_W}
          aria-valuemax={MAX_PANEL_W}
          tabIndex={0}
          onPointerDown={e => { e.preventDefault(); setDragging(true) }}
          onKeyDown={onSeparatorKeyDown}
          style={{
            position: 'absolute', top: 0, bottom: 0, width: 7, zIndex: 2,
            [side === 'right' ? 'left' : 'right']: -3,
            cursor: 'col-resize', background: dragging ? 'var(--accent)' : 'transparent',
            opacity: dragging ? 0.5 : 1,
          }}
        />
      )}
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
        title={open ? `Collapse ${title}` : `Expand ${title}`}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: side === 'right' && open ? 'flex-start' : 'center',
          gap: 4, flexShrink: 0, width: '100%', padding: '5px 4px',
          background: 'none', border: 'none', borderBottom: '1px solid var(--border)',
          color: 'var(--muted)', cursor: 'pointer', font: 'inherit', fontSize: 10,
        }}
      >
        {/* Icon-only by design. Both panels already head their own content ("Fields",
            "Widget", "Page"), so a visible title here would duplicate an existing
            heading -- ambiguous to a reader and to any by-text query. The name lives
            on aria-label instead, where it stays available to assistive tech. */}
        <Chevron size={13} aria-hidden />
      </button>

      {/* Kept mounted while collapsed so in-progress edits and scroll positions survive. */}
      <div
        ref={scrollRef}
        aria-label={title}
        aria-hidden={!open}
        style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: open ? 'block' : 'none' }}
      >
        {children}
      </div>
    </div>
  )
}
