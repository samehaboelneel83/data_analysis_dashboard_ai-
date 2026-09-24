/**
 * CrossFilterContext
 * ------------------
 * Page-level state that tracks:
 *   activeFilters : column → value filters currently applied (emitted by clicks)
 *   interactions  : widgetId → { broadcasts, receives }
 *
 * Any widget that "broadcasts" emits filters when the user clicks a data point.
 * Any widget that "receives" re-queries with the active filters applied on top
 * of its own config filters.
 *
 * Two-way  = broadcasts AND receives
 * One-way source = broadcasts, does NOT receive
 * One-way sink   = does NOT broadcast, receives
 * Isolated = neither
 */

import React, { createContext, useContext, useState, useCallback, useMemo, useRef } from 'react'

export interface ActiveFilter {
  column: string
  value: unknown | unknown[]
  label: string          // human-readable "Region = North"
  sourceWidgetId: number
  sourcePageId: number
}

export interface WidgetInteraction {
  broadcasts: boolean   // this widget emits cross-filters on click
  receives:   boolean   // this widget reacts to cross-filters from others
  syncAllPages?: boolean // this widget's filter reaches every page, not just its own
  /** How an incoming selection is applied: 'filter' narrows the widget to the
      selection; 'highlight' keeps the full result and saturates the selected
      share of each mark (SAS's linked selection, Power BI's default). */
  receiveMode?: 'filter' | 'highlight'
  /** Named per-pair actions (SAS's Actions pane): when non-empty, this
      widget's selections reach ONLY the listed targets, each with its own
      action type — defining explicit actions replaces broadcast-to-all,
      exactly as adding actions does in SAS. */
  actions?: { targetId: number; mode: 'filter' | 'highlight' }[]
}

/** Whether `target` is reachable from `source` through per-pair action edges.
 *  Actions are transitive, as SAS documents them: if A defines an action on B and
 *  B defines one on C, a selection in A reaches C as well. Walks the directed
 *  action graph breadth-first with a visited set, so a cycle (A→B, B→A) terminates
 *  instead of looping. `source` is excluded from its own reach by the caller. */
function actionReaches(
  source: number, target: number,
  interactions: Record<number, WidgetInteraction>,
): boolean {
  const seen = new Set<number>([source])
  const stack: number[] = [source]
  while (stack.length) {
    const cur = stack.pop() as number
    for (const a of interactions[cur]?.actions ?? []) {
      if (a.targetId === target) return true
      if (!seen.has(a.targetId)) { seen.add(a.targetId); stack.push(a.targetId) }
    }
  }
  return false
}

/** Page-wide automatic action mode (SAS's page-level setting, mutually
    exclusive with manual per-widget actions):
      manual  per-widget InteractionSettings apply (the default)
      linked  every widget broadcasts; receivers HIGHLIGHT the selection
      oneway  every widget broadcasts filters, single source at a time --
              a new selection replaces filters from other sources
      twoway  every widget broadcasts and receives; filters accumulate */
export type PageInteractionMode = 'manual' | 'linked' | 'oneway' | 'twoway'

interface CrossFilterState {
  activeFilters:   ActiveFilter[]
  interactions:    Record<number, WidgetInteraction>
  pageMode:        PageInteractionMode
  getReceiveMode:  (widgetId: number) => 'filter' | 'highlight'

  emitFilter:      (widgetId: number, pageId: number, column: string, value: unknown, label: string) => void
  emitMultiFilter: (widgetId: number, pageId: number, column: string, values: unknown[], label: string) => void
  clearFilter:     (column: string, sourceWidgetId: number) => void
  clearAllFilters: () => void

  /** Reader-side undo (Phase 1 item 4): step back and forward through the
   *  reader's own selections -- clicks, clears, "clear all" -- without
   *  touching anything the author saved. */
  /** A page link's "carry my selections": re-scope this page's selections to
   *  the target page, so the reader lands on it still filtered the same way. */
  carryFiltersTo:  (fromPageId: number, toPageId: number) => void
  undoSelection:   () => void
  redoSelection:   () => void
  /** What an undo would put back, as a sentence; null when there is nothing. */
  undoLabel:       string | null
  redoLabel:       string | null

  setInteraction:  (widgetId: number, interaction: WidgetInteraction) => void
  /** Set WITHOUT writing it down. For defaults and hydration -- a value the
   *  user did not choose must not rewrite their widget's config. */
  initInteraction: (widgetId: number, interaction: WidgetInteraction) => void
  getFiltersFor:   (widgetId: number, currentPageId: number) => ActiveFilter[]  // only filters from OTHER widgets, scoped to this page unless synced
  canBroadcast:    (widgetId: number) => boolean
  canReceive:      (widgetId: number) => boolean
}

const CrossFilterContext = createContext<CrossFilterState | null>(null)

/** Selections kept for undo; a reader session is short, but unbounded is wrong. */
const SELECTION_HISTORY = 50

/** The state an undo returns to, in words: "region is Asia Pacific", or no selections. */
export function describeSelection(state: ActiveFilter[]): string {
  if (state.length === 0) return 'no selections'
  const names = state.map(f => f.label)
  return names.length <= 2 ? names.join(' and ') : `${names.slice(0, 2).join(', ')} and ${names.length - 2} more`
}

/** The interactions the page's widgets were saved with.
 *
 *  Read straight out of `config.interaction` at mount, BEFORE any child renders
 *  -- `InteractionSettings` defaults a widget the first time its panel opens,
 *  and a value that arrived later would be overwritten by that default while
 *  the user watched. */
function storedInteractions(widgets?: { id: number; config?: unknown }[]) {
  const out: Record<number, WidgetInteraction> = {}
  for (const w of widgets ?? []) {
    const stored = (w.config as { interaction?: unknown } | undefined)?.interaction
    if (stored && typeof stored === 'object' && !Array.isArray(stored)) {
      out[w.id] = stored as WidgetInteraction
    }
  }
  return out
}

export function CrossFilterProvider(
  { children, pageMode = 'manual', widgets, onPersistInteraction }: {
    children: React.ReactNode
    pageMode?: PageInteractionMode
    /** The page's widgets, so saved interactions can be restored. */
    widgets?: { id: number; config?: unknown }[]
    /** Called when the USER changes an interaction, so it can be written to
     *  the widget's config. Absent in read-only surfaces, where nothing saves. */
    onPersistInteraction?: (widgetId: number, interaction: WidgetInteraction) => void
  },
) {
  const [activeFilters, setActiveFiltersRaw] = useState<ActiveFilter[]>([])
  // Selection history for the reader's undo. Refs, not state updaters with
  // side effects: a React StrictMode double-invoke must not record twice.
  const current = useRef<ActiveFilter[]>([])
  const past = useRef<ActiveFilter[][]>([])
  const future = useRef<ActiveFilter[][]>([])
  const [, bumpHistory] = useState(0)
  const setActiveFilters = useCallback((next: ActiveFilter[] | ((prev: ActiveFilter[]) => ActiveFilter[])) => {
    const prev = current.current
    const value = typeof next === 'function' ? (next as (p: ActiveFilter[]) => ActiveFilter[])(prev) : next
    if (JSON.stringify(value) === JSON.stringify(prev)) return
    past.current = [...past.current, prev].slice(-SELECTION_HISTORY)
    future.current = []
    current.current = value
    setActiveFiltersRaw(value)
    bumpHistory(n => n + 1)
  }, [])
  const undoSelection = useCallback(() => {
    const prev = past.current[past.current.length - 1]
    if (!prev) return
    past.current = past.current.slice(0, -1)
    future.current = [current.current, ...future.current]
    current.current = prev
    setActiveFiltersRaw(prev)
    bumpHistory(n => n + 1)
  }, [])
  const redoSelection = useCallback(() => {
    const next = future.current[0]
    if (!next) return
    future.current = future.current.slice(1)
    past.current = [...past.current, current.current]
    current.current = next
    setActiveFiltersRaw(next)
    bumpHistory(n => n + 1)
  }, [])
  const undoLabel = past.current.length ? describeSelection(past.current[past.current.length - 1]) : null
  const redoLabel = future.current.length ? describeSelection(future.current[0]) : null
  // Lazy initialiser, not an effect: the map exists on the first render, which
  // is what closes the race with the settings panel's default.
  const [interactions,  setInteractions]  = useState<Record<number, WidgetInteraction>>(
    () => storedInteractions(widgets))

  const _setFilter = useCallback((widgetId: number, pageId: number, column: string, value: unknown | unknown[], label: string) => {
    // Page modes override per-widget settings (SAS: mutually exclusive with
    // manual actions) -- under any automatic mode every widget broadcasts.
    if (pageMode === 'manual' && !(interactions[widgetId]?.broadcasts ?? true)) return
    setActiveFilters(prev => {
      // One-way: single source at a time -- a selection on a new widget
      // replaces every other source's filters instead of accumulating.
      const base = pageMode === 'oneway' ? prev.filter(f => f.sourceWidgetId === widgetId) : prev
      // Replace any existing filter for same column from same source
      const without = base.filter(f => !(f.column === column && f.sourceWidgetId === widgetId))
      // Toggle: if same value already active, clear it (click again to deselect)
      const existing = base.find(f => f.column === column && f.sourceWidgetId === widgetId && JSON.stringify(f.value) === JSON.stringify(value))
      if (existing) return without
      return [...without, { column, value, label, sourceWidgetId: widgetId, sourcePageId: pageId }]
    })
  }, [interactions, pageMode])

  const emitFilter = useCallback((widgetId: number, pageId: number, column: string, value: unknown, label: string) => {
    _setFilter(widgetId, pageId, column, value, label)
  }, [_setFilter])

  const emitMultiFilter = useCallback((widgetId: number, pageId: number, column: string, values: unknown[], label: string) => {
    // An empty selection is the absence of a filter. Storing it as one would put
    // a value-less predicate on the page that no widget can satisfy, so it is
    // cleared here too -- callers should not each have to remember.
    if (values.length === 0) {
      setActiveFilters(prev => prev.filter(f => !(f.column === column && f.sourceWidgetId === widgetId)))
      return
    }
    _setFilter(widgetId, pageId, column, values, label)
  }, [_setFilter])

  const clearFilter = useCallback((column: string, sourceWidgetId: number) => {
    setActiveFilters(prev => prev.filter(f => !(f.column === column && f.sourceWidgetId === sourceWidgetId)))
  }, [])

  const clearAllFilters = useCallback(() => setActiveFilters([]), [])

  const carryFiltersTo = useCallback((fromPageId: number, toPageId: number) => {
    if (fromPageId === toPageId) return
    setActiveFilters(prev => {
      const carried = prev.filter(f => f.sourcePageId === fromPageId)
        .map(f => ({ ...f, sourcePageId: toPageId }))
      if (!carried.length) return prev
      // Replace what the target page already had from the same source+column.
      const kept = prev.filter(f => !(f.sourcePageId === toPageId
        && carried.some(c => c.column === f.column && c.sourceWidgetId === f.sourceWidgetId)))
      return [...kept, ...carried]
    })
  }, [setActiveFilters])

  const setInteraction = useCallback((widgetId: number, interaction: WidgetInteraction) => {
    setInteractions(prev => ({ ...prev, [widgetId]: interaction }))
    onPersistInteraction?.(widgetId, interaction)
  }, [onPersistInteraction])

  const initInteraction = useCallback((widgetId: number, interaction: WidgetInteraction) => {
    // Local only. Defaulting a widget nobody has configured is a convenience;
    // saving it would rewrite every config the moment a tile is clicked.
    setInteractions(prev => (prev[widgetId] ? prev : { ...prev, [widgetId]: interaction }))
  }, [])

  const getFiltersFor = useCallback((widgetId: number, currentPageId: number): ActiveFilter[] => {
    if (pageMode === 'manual' && !(interactions[widgetId]?.receives ?? true)) return []
    // Only receive filters emitted by OTHER widgets, scoped to the current page unless the
    // source widget is marked to sync across all pages. A source with explicit
    // per-pair actions reaches only its listed targets (page modes override).
    return activeFilters.filter(f => {
      if (f.sourceWidgetId === widgetId) return false
      if (!(f.sourcePageId === currentPageId || interactions[f.sourceWidgetId]?.syncAllPages)) return false
      const acts = interactions[f.sourceWidgetId]?.actions
      if (pageMode === 'manual' && acts && acts.length > 0) {
        // Direct OR transitive: a source with explicit actions reaches its listed
        // targets and anything they in turn act upon (SAS's transitive actions).
        return actionReaches(f.sourceWidgetId, widgetId, interactions)
      }
      return true
    })
  }, [activeFilters, interactions, pageMode])

  const canBroadcast = useCallback((id: number) =>
    pageMode !== 'manual' || (interactions[id]?.broadcasts ?? true), [interactions, pageMode])
  const canReceive   = useCallback((id: number) =>
    pageMode !== 'manual' || (interactions[id]?.receives   ?? true), [interactions, pageMode])
  const getReceiveMode = useCallback((id: number): 'filter' | 'highlight' => {
    if (pageMode === 'linked') return 'highlight'
    if (pageMode === 'oneway' || pageMode === 'twoway') return 'filter'
    // A per-pair action's type wins for the filters it delivers: when every
    // source currently reaching this widget declares 'highlight' for it, the
    // widget highlights; one 'filter' pair keeps the safer narrowing mode.
    const pairModes = activeFilters
      .map(f => interactions[f.sourceWidgetId]?.actions?.find(a => a.targetId === id)?.mode)
      .filter((m): m is 'filter' | 'highlight' => m != null)
    if (pairModes.length > 0) return pairModes.every(m => m === 'highlight') ? 'highlight' : 'filter'
    return interactions[id]?.receiveMode ?? 'filter'
  }, [interactions, pageMode, activeFilters])

  // The value is memoized because every consumer re-renders when it changes
  // identity: an inline object literal here would re-render every widget on
  // every provider render, defeating React.memo on WidgetRenderer entirely.
  const value = useMemo(() => ({
    activeFilters, interactions, pageMode, getReceiveMode,
    emitFilter, emitMultiFilter, clearFilter, clearAllFilters, carryFiltersTo,
    undoSelection, redoSelection, undoLabel, redoLabel,
    setInteraction, initInteraction, getFiltersFor, canBroadcast, canReceive,
  }), [activeFilters, interactions, pageMode, getReceiveMode, emitFilter, emitMultiFilter, clearFilter,
       clearAllFilters, carryFiltersTo, undoSelection, redoSelection, undoLabel, redoLabel,
       setInteraction, initInteraction, getFiltersFor,
       canBroadcast, canReceive])

  return (
    <CrossFilterContext.Provider value={value}>
      {children}
    </CrossFilterContext.Provider>
  )
}

export function useCrossFilter() {
  const ctx = useContext(CrossFilterContext)
  if (!ctx) throw new Error('useCrossFilter must be used inside CrossFilterProvider')
  return ctx
}
