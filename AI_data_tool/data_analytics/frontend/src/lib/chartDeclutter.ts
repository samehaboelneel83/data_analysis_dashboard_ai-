/**
 * Pixel-true label declutter for every Recharts chart (QA 2026-09-26).
 *
 * The renderers thin data labels by COUNT (`labelStride`: at most ~12), which
 * cannot know that seven small bars squeezed into 60px still print seven
 * numbers on top of each other, or that the tallest bar's value lands on the
 * "12,000,000" tick. Only the drawn SVG knows where text really is, so this
 * pass runs after each redraw and resize, measures, and hides what collides:
 *
 *  1. Data labels (bar/line/area values, pie labels) are placed greedily,
 *     biggest magnitude first -- the numbers a reader most wants survive. A
 *     label that is clipped by the tile, or overlaps a label already kept,
 *     is hidden.
 *  2. Axis ticks yield to kept data labels: a tick is a guide, the label is
 *     the reading.
 *  3. Ticks on one axis that overlap each other are thinned in order.
 *
 * Hidden text keeps its node (visibility only), so tooltips, the accessible
 * table and a later re-layout that has room again are unaffected; each pass
 * first restores everything it hid last time.
 */

const HID = 'data-dl-declutter'
const PAD = 2
const MAX_LABELS = 600

type Box = { l: number; t: number; r: number; b: number }

function box(el: Element): Box | null {
  const r = el.getBoundingClientRect()
  if (!(r.width > 0 && r.height > 0)) return null
  return { l: r.left, t: r.top, r: r.right, b: r.bottom }
}
const hit = (a: Box, b: Box) =>
  a.l < b.r + PAD && b.l < a.r + PAD && a.t < b.b + PAD && b.t < a.b + PAD
const inside = (a: Box, c: Box) =>
  a.l >= c.l - 1 && a.r <= c.r + 1 && a.t >= c.t - 1 && a.b <= c.b + 1

function hide(el: Element) {
  const h = el as HTMLElement | SVGElement
  if (h.style.visibility === 'hidden') return
  h.setAttribute(HID, h.style.visibility || '-')
  h.style.visibility = 'hidden'
}

function magnitude(text: string): number {
  const m = text.replace(/[\s,٬ ]/g, '').match(/-?\d+(\.\d+)?/)
  if (!m) return 0
  let v = Math.abs(parseFloat(m[0]))
  if (/[kK]\b|ألف/.test(text)) v *= 1e3
  if (/M\b|مليون/.test(text)) v *= 1e6
  if (/B\b|مليار/.test(text)) v *= 1e9
  return v
}

export function declutterChart(root: HTMLElement): void {
  // Undo the previous pass.
  root.querySelectorAll(`[${HID}]`).forEach(el => {
    const prev = el.getAttribute(HID)
    ;(el as HTMLElement).style.visibility = prev === '-' ? '' : (prev ?? '')
    el.removeAttribute(HID)
  })
  const frame = box(root)
  if (!frame) return

  root.querySelectorAll('svg.recharts-surface').forEach(svg => {
    const labelNodes = Array.from(svg.querySelectorAll(
      '.recharts-label-list text, .recharts-pie-labels text, text.recharts-pie-label-text'))
      .filter(t => (t.textContent ?? '').trim() !== '')
    if (labelNodes.length > MAX_LABELS) return

    const labels = labelNodes
      .map(t => ({ el: t, hideEl: t.closest('.recharts-pie-labels > g') ?? t,
                   b: box(t), v: magnitude(t.textContent ?? '') }))
      .filter((x): x is { el: Element; hideEl: Element; b: Box; v: number } => x.b !== null)
      .sort((a, b) => b.v - a.v)

    const kept: Box[] = []
    for (const l of labels) {
      if (!inside(l.b, frame) || kept.some(k => hit(k, l.b))) { hide(l.hideEl); continue }
      kept.push(l.b)
    }

    svg.querySelectorAll('.recharts-cartesian-axis').forEach(axis => {
      const ticks = Array.from(axis.querySelectorAll('.recharts-cartesian-axis-tick text'))
      let last: Box | null = null
      for (const t of ticks) {
        const b = box(t)
        if (!b) continue
        if (kept.some(k => hit(k, b))) { hide(t); continue }
        // A slanted tick's bounding box is a big diagonal rectangle; boxes of
        // neighbours overlap long before the glyphs do. The axis planner
        // already spaces slanted labels, so only upright ones are thinned here.
        const slanted = /rotate\(\s*-?[1-9]/.test(t.getAttribute('transform') ?? '')
        if (!slanted && last && hit(last, b)) { hide(t); continue }
        last = b
      }
    })
  })
}

/** Watch `root` and declutter after every redraw and resize, once per frame. */
export function watchDeclutter(root: HTMLElement): () => void {
  let raf = 0
  const run = () => {
    if (raf) return
    raf = requestAnimationFrame(() => { raf = 0; try { declutterChart(root) } catch { /* never break a chart */ } })
  }
  const mo = typeof MutationObserver === 'undefined' ? null
    : new MutationObserver(run)
  // characterData: a label's number can change in place; attributes are NOT
  // observed, so the pass's own visibility writes cannot retrigger it.
  mo?.observe(root, { childList: true, subtree: true, characterData: true })
  const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(run)
  ro?.observe(root)
  run()
  // Recharts animates bars in and positions labels at the end; catch it.
  const late = setTimeout(run, 1600)
  return () => { mo?.disconnect(); ro?.disconnect(); clearTimeout(late); if (raf) cancelAnimationFrame(raf) }
}
