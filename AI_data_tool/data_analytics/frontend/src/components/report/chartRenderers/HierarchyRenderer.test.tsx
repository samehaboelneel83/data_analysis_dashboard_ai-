/**
 * Circle packing: the geometry has to mean what it claims.
 *
 * A partition chart's whole argument is that area IS value. The shaper already
 * refuses non-additive aggregations for exactly that reason, which makes the
 * refusal worthless if the renderer then draws areas that do not match the
 * numbers it was handed. These assertions read the drawn `r`/`cx`/`cy` rather
 * than a snapshot, because a snapshot would lock in whatever the code does —
 * including a lie — and re-bless it on every change.
 *
 * Two properties, both checkable without layout (jsdom has none, but these
 * coordinates are computed, not measured):
 *
 *   1. Between siblings, the ratio of AREAS equals the ratio of values.
 *   2. Every child circle lies wholly inside its parent's.
 *
 * Sibling-only is the honest scope, and it is what d3's pack does too: children
 * are scaled to fit their parent, so a circle in one branch is not comparable
 * with one in another. Claiming more would be the lie this file exists to stop.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import HierarchyRenderer from './HierarchyRenderer'

/** The props every chart renderer is handed. Spelled out rather than cast to
 *  `never`: a cast would keep compiling after the contract changes, and the
 *  first sign would be a renderer crashing on a prop the test said existed. */
const props = (data: unknown) => ({
  rows: [], data, cfg: {}, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: vi.fn(),
})

const data = (type: string) => ({
  type,
  root: {
    name: 'root', value: 100, depth: 0,
    children: [
      { name: 'Big', value: 75, depth: 1, children: [] },
      { name: 'Small', value: 25, depth: 1, children: [] },
    ],
  },
})

function circlesOf(container: HTMLElement) {
  return Array.from(container.querySelectorAll('circle')).map(c => ({
    r: Number(c.getAttribute('r')),
    cx: Number(c.getAttribute('cx')),
    cy: Number(c.getAttribute('cy')),
    label: c.querySelector('title')?.textContent ?? '',
  }))
}

describe('circle packing', () => {
  it('draws a circle per node and names each with its value', () => {
    const { container } = render(
      <HierarchyRenderer {...props(data('circle_pack'))} />)
    const circles = circlesOf(container)

    expect(circles.length).toBeGreaterThanOrEqual(3)   // root + two children
    expect(circles.some(c => /Big/.test(c.label))).toBe(true)
    expect(circles.some(c => /Small/.test(c.label))).toBe(true)
  })

  it('gives siblings areas in the same ratio as their values', () => {
    // 75 vs 25 is 3:1 by AREA, so √3 : 1 by radius. Getting this wrong by
    // using radius directly would draw Big three times as wide and NINE times
    // the area — the classic bubble-chart lie, in a chart whose only job is
    // area.
    const { container } = render(
      <HierarchyRenderer {...props(data('circle_pack'))} />)
    const circles = circlesOf(container)
    const big = circles.find(c => /Big/.test(c.label))!
    const small = circles.find(c => /Small/.test(c.label))!

    const areaRatio = (big.r * big.r) / (small.r * small.r)
    expect(areaRatio).toBeCloseTo(3, 1)
  })

  it('keeps every child wholly inside its parent', () => {
    // A child spilling over its parent's edge says the part is bigger than the
    // whole. It is the one way this layout can contradict itself on screen.
    const { container } = render(
      <HierarchyRenderer {...props(data('circle_pack'))} />)
    const circles = circlesOf(container)
    const parent = circles.reduce((a, b) => (a.r >= b.r ? a : b))
    const children = circles.filter(c => c !== parent && c.label)

    expect(children.length).toBe(2)
    for (const c of children) {
      const dist = Math.hypot(c.cx - parent.cx, c.cy - parent.cy)
      expect(dist + c.r).toBeLessThanOrEqual(parent.r + 0.01)
    }
  })

  it('survives a node whose value is missing', () => {
    // `value` is `number | null` in the contract — a level with no measure, or
    // a node the aggregation could not fill. Drawing NaN radii would empty the
    // chart with no explanation.
    const { container } = render(<HierarchyRenderer {...props({
      type: 'circle_pack',
      root: { name: 'root', value: null, depth: 0, children: [
        { name: 'A', value: null, depth: 1, children: [] },
        { name: 'B', value: 10, depth: 1, children: [] },
      ] },
    })} />)

    for (const c of circlesOf(container)) {
      expect(Number.isFinite(c.r)).toBe(true)
      expect(c.r).toBeGreaterThanOrEqual(0)
    }
  })

  it('leaves the other layouts alone', () => {
    // One renderer, six layouts, switched on data.type. A sunburst must not
    // start drawing circles because a sibling branch was added.
    const { container } = render(
      <HierarchyRenderer {...props(data('sunburst'))} />)
    expect(container.querySelectorAll('circle').length).toBe(0)
    expect(container.querySelector('svg')?.getAttribute('aria-label'))
      .toMatch(/sunburst/i)
  })
})
