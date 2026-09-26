/**
 * Draw-time thinning for point charts (QA 2026-09-26: "all data makes the app
 * very slow").
 *
 * The data stays complete -- every row is fetched, counted and in the tooltip
 * math. What changes is how many SVG shapes are DRAWN: two points closer than
 * a pixel or two land on the same spot on screen, and drawing both costs a DOM
 * node and a layout pass while showing nothing new. 5,670 circles per scatter
 * froze the page for ~1s per redraw, and a resize redraws every frame.
 *
 * Points are binned on a grid of `cell` pixels over the plot area and the
 * first point in each bin is drawn. The picture is the same to the eye; the
 * shape count drops to at most (plotW/cell) x (plotH/cell) and, for the usual
 * clustered data, to a few hundred. Below `threshold` nothing is thinned.
 */
export const THIN_THRESHOLD = 1500

export function thinPoints<T extends { x: unknown; y: unknown }>(
  points: T[], plotW = 600, plotH = 300, cell = 2, threshold = THIN_THRESHOLD,
): { points: T[]; index: number[] } {
  const n = points.length
  const all = () => ({ points, index: points.map((_p, i) => i) })
  if (n <= threshold) return all()
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
  for (const p of points) {
    const x = Number(p.x), y = Number(p.y)
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue
    if (x < xMin) xMin = x
    if (x > xMax) xMax = x
    if (y < yMin) yMin = y
    if (y > yMax) yMax = y
  }
  if (!Number.isFinite(xMin) || !Number.isFinite(yMin)) return all()
  const cols = Math.max(1, Math.floor(plotW / cell)), rows = Math.max(1, Math.floor(plotH / cell))
  const sx = xMax > xMin ? (cols - 1) / (xMax - xMin) : 0
  const sy = yMax > yMin ? (rows - 1) / (yMax - yMin) : 0
  const seen = new Set<number>()
  const out: T[] = [], index: number[] = []
  points.forEach((p, i) => {
    const x = Number(p.x), y = Number(p.y)
    if (!Number.isFinite(x) || !Number.isFinite(y)) return
    const key = Math.round((x - xMin) * sx) * rows + Math.round((y - yMin) * sy)
    if (seen.has(key)) return
    seen.add(key)
    out.push(p); index.push(i)
  })
  return { points: out, index }
}

/** Animating thousands of shapes is what makes a large chart feel frozen. */
export const ANIMATE_MAX_POINTS = 400
