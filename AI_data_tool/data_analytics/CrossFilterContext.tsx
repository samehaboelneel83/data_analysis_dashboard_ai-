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

import React, { createContext, useContext, useState, useCallback } from 'react'

export interface ActiveFilter {
  column: string
  value: unknown
  label: string          // human-readable "Region = North"
  sourceWidgetId: number
}

export interface WidgetInteraction {
  broadcasts: boolean   // this widget emits cross-filters on click
  receives:   boolean   // this widget reacts to cross-filters from others
}

interface CrossFilterState {
  activeFilters:   ActiveFilter[]
  interactions:    Record<number, WidgetInteraction>

  emitFilter:      (widgetId: number, column: string, value: unknown, label: string) => void
  clearFilter:     (column: string, sourceWidgetId: number) => void
  clearAllFilters: () => void

  setInteraction:  (widgetId: number, interaction: WidgetInteraction) => void
  getFiltersFor:   (widgetId: number) => ActiveFilter[]  // only filters from OTHER widgets
  canBroadcast:    (widgetId: number) => boolean
  canReceive:      (widgetId: number) => boolean
}

const CrossFilterContext = createContext<CrossFilterState | null>(null)

export function CrossFilterProvider({ children }: { children: React.ReactNode }) {
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [interactions,  setInteractions]  = useState<Record<number, WidgetInteraction>>({})

  const emitFilter = useCallback((widgetId: number, column: string, value: unknown, label: string) => {
    if (!interactions[widgetId]?.broadcasts) return
    setActiveFilters(prev => {
      // Replace any existing filter for same column from same source
      const without = prev.filter(f => !(f.column === column && f.sourceWidgetId === widgetId))
      // Toggle: if same value already active, clear it (click again to deselect)
      const existing = prev.find(f => f.column === column && f.sourceWidgetId === widgetId && f.value === value)
      if (existing) return without
      return [...without, { column, value, label, sourceWidgetId: widgetId }]
    })
  }, [interactions])

  const clearFilter = useCallback((column: string, sourceWidgetId: number) => {
    setActiveFilters(prev => prev.filter(f => !(f.column === column && f.sourceWidgetId === sourceWidgetId)))
  }, [])

  const clearAllFilters = useCallback(() => setActiveFilters([]), [])

  const setInteraction = useCallback((widgetId: number, interaction: WidgetInteraction) => {
    setInteractions(prev => ({ ...prev, [widgetId]: interaction }))
  }, [])

  const getFiltersFor = useCallback((widgetId: number): ActiveFilter[] => {
    if (!interactions[widgetId]?.receives) return []
    // Only receive filters emitted by OTHER widgets
    return activeFilters.filter(f => f.sourceWidgetId !== widgetId)
  }, [activeFilters, interactions])

  const canBroadcast = useCallback((id: number) => interactions[id]?.broadcasts ?? true, [interactions])
  const canReceive   = useCallback((id: number) => interactions[id]?.receives   ?? true, [interactions])

  return (
    <CrossFilterContext.Provider value={{
      activeFilters, interactions,
      emitFilter, clearFilter, clearAllFilters,
      setInteraction, getFiltersFor, canBroadcast, canReceive,
    }}>
      {children}
    </CrossFilterContext.Provider>
  )
}

export function useCrossFilter() {
  const ctx = useContext(CrossFilterContext)
  if (!ctx) throw new Error('useCrossFilter must be used inside CrossFilterProvider')
  return ctx
}
