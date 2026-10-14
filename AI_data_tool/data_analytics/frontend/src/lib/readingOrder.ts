/**
 * QA3 A8: the order a reader scans a page in: top to bottom, then from the
 * start of the line to its end (right to left in Arabic). The canvas is not
 * mirrored in RTL (v1), so "start" is the right edge there.
 *
 * Callers pass the layout the canvas DRAWS (a page still auto-packed is not
 * where its stored layout says), so the order follows every move.
 */
interface Placed { id: number; layout: { x: number; y: number; w: number; h: number } }

export function readingOrder<T extends Placed>(widgets: readonly T[], rtl: boolean): T[] {
  return [...widgets].sort((a, b) =>
    a.layout.y - b.layout.y
    || (rtl ? (b.layout.x + b.layout.w) - (a.layout.x + a.layout.w) : a.layout.x - b.layout.x)
    || a.id - b.id)
}

/** The author's own Tab order when one was set (any widget with a `tabIndex`);
 *  widgets without one follow in reading order. Without one, reading order. */
export function tabOrder<T extends Placed & { config?: unknown }>(widgets: readonly T[], rtl: boolean): T[] {
  const idx = (w: T) => (w.config as { tabIndex?: number } | null | undefined)?.tabIndex
  const scanned = readingOrder(widgets, rtl)
  if (!scanned.some(w => idx(w) != null)) return scanned
  const pos = new Map(scanned.map((w, i) => [w.id, i]))
  return [...scanned].sort((a, b) =>
    (idx(a) ?? Infinity) - (idx(b) ?? Infinity) || pos.get(a.id)! - pos.get(b.id)!)
}
