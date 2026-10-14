/**
 * QA3 A1: the canvas selection as one rule.
 *
 * The builder keeps a primary widget (what Properties shows) and a set for a
 * multi-selection. Before this, a plain click set only the primary and a
 * Shift+click added only the clicked widget to the set, so the first widget
 * was highlighted but never counted ("1 selected" with two outlined).
 *
 * Now the set, when it is in use, always holds every selected widget,
 * including the primary, and the primary is the last one added: Properties
 * follows the latest click and the status bar counts what is outlined.
 */
export interface CanvasSelection {
  primary: number | null
  /** Empty for a single selection; otherwise every selected id, in order. */
  multi: ReadonlySet<number>
}

export const EMPTY_SELECTION: CanvasSelection = { primary: null, multi: new Set() }

export function clickSelection(sel: CanvasSelection, id: number, additive: boolean): CanvasSelection {
  if (!additive) return { primary: id, multi: new Set() }
  const members = sel.multi.size ? [...sel.multi] : (sel.primary != null ? [sel.primary] : [])
  const removed = members.includes(id)
  const next = removed ? members.filter(m => m !== id) : [...members, id]
  if (next.length === 0) return EMPTY_SELECTION
  if (next.length === 1) return { primary: next[0], multi: new Set() }
  return { primary: removed ? next[next.length - 1] : id, multi: new Set(next) }
}

export function selectionCount(sel: CanvasSelection): number {
  return sel.multi.size || (sel.primary != null ? 1 : 0)
}
