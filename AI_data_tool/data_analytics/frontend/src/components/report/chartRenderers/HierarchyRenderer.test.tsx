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
import { render, fireEvent } from '@testing-library/react'
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

describe('hierarchy plan, step 4: ticks that filter, click-to-zoom (2026-10-10)', () => {
  const leaf = (name: string, value: number, depth: number) => ({ name, value, depth, children: [] })
  const geo = { name: '', value: 10, depth: 0, children: [
    { name: 'Egypt', value: 6, depth: 0, children: [leaf('Alexandria', 2, 1), leaf('Cairo', 4, 1)] },
    { name: 'US', value: 4, depth: 0, children: [leaf('Alexandria', 1, 1), leaf('Boston', 3, 1)] },
  ] }

  it('a tree tick sends the exact branch, and a part-ticked parent shows a dash', () => {
    const onTreeChange = vi.fn()
    const { getByLabelText, rerender } = render(
      <HierarchyRenderer {...props({ type: 'tree', root: geo })} treePaths={null} onTreeChange={onTreeChange} />)
    fireEvent.click(getByLabelText('US › Alexandria'))
    expect(onTreeChange).toHaveBeenLastCalledWith([['US', 'Alexandria']])
    rerender(<HierarchyRenderer {...props({ type: 'tree', root: geo })} treePaths={[['US', 'Alexandria']]} onTreeChange={onTreeChange} />)
    expect((getByLabelText('US') as HTMLInputElement).indeterminate).toBe(true)
    expect((getByLabelText('Egypt › Alexandria') as HTMLInputElement).checked).toBe(false)
    fireEvent.click(getByLabelText('Egypt'))
    expect(onTreeChange).toHaveBeenLastCalledWith([['Egypt'], ['US', 'Alexandria']])
  })

  it('a tree with nothing to filter by draws no boxes', () => {
    const { queryAllByRole } = render(<HierarchyRenderer {...props({ type: 'tree', root: geo })} />)
    expect(queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('a sunburst zooms into a ring and back out from the centre or the trail', () => {
    const { getByRole, queryByRole } = render(<HierarchyRenderer {...props({ type: 'sunburst', root: geo })} />)
    fireEvent.click(getByRole('button', { name: 'Zoom into Egypt' }))
    expect(getByRole('navigation').textContent).toContain('Egypt')
    expect(queryByRole('button', { name: 'Zoom into US' })).toBeNull()
    fireEvent.click(getByRole('button', { name: 'Zoom out' }))
    expect(queryByRole('navigation')).toBeNull()
    fireEvent.click(getByRole('button', { name: 'Zoom into US' }))
    fireEvent.click(getByRole('button', { name: 'All' }))
    expect(queryByRole('navigation')).toBeNull()
  })

  it('an icicle zooms into a block', () => {
    const { getByRole, container } = render(<HierarchyRenderer {...props({ type: 'icicle', root: geo })} />)
    fireEvent.click(getByRole('button', { name: 'Zoom into US' }))
    expect(container.textContent).toContain('Boston')
    expect(container.textContent).not.toContain('Cairo')
  })
})

it('a sunburst with an only child still draws its ring', () => {
  const { container } = render(<HierarchyRenderer {...props({ type: 'sunburst', root: { name: '', value: 5, depth: 0,
    children: [{ name: 'Europe', value: 5, depth: 0, children: [{ name: 'Germany', value: 5, depth: 1, children: [] }] }] } })} />)
  const d = Array.from(container.querySelectorAll('path')).map(p => p.getAttribute('d') ?? '')
  expect(d).toHaveLength(2)
  // Two half-arcs each, so the ring is not a zero-length path.
  d.forEach(x => expect(x.match(/A/g)!.length).toBe(4))
})
