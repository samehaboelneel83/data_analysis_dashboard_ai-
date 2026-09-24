import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Lineage from './Lineage'
import { DirectionProvider } from '../contexts/DirectionContext'
import { lineageApi } from '../services/api'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({ lineageApi: { graph: vi.fn() } }))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(lineageApi.graph).mockResolvedValue({
    sources: [{ id: 1, name: 'Warehouse', type: 'postgres' }],
    datasets: [
      {
        id: 5, name: 'Orders', mode: 'import', source_id: 1, joins: [6],
        extraction_kind: 'query',
        transform: { count: 2, kinds: ['filter_rows', 'sort'] },
        load: { last_refreshed_at: new Date(Date.now() - 2 * 3600_000).toISOString(), strategy: 'incremental', cursor_column: 'updated_at', staleness: 'fresh' },
      },
      {
        id: 6, name: 'Customers', mode: 'import', source_id: null, joins: [],
        extraction_kind: 'csv',
        transform: { count: 0, kinds: [] },
        load: { last_refreshed_at: null, strategy: null, cursor_column: null, staleness: 'never' },
      },
    ],
    reports: [{ id: 9, name: 'Sales', dataset_ids: [5] }],
  })
})

describe('Lineage', () => {
  it('renders the three columns with nodes and edge annotations', async () => {
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    expect(await screen.findByText('Warehouse')).toBeInTheDocument()
    expect(screen.getByText('Orders')).toBeInTheDocument()
    expect(screen.getByText(/joins 1/)).toBeInTheDocument()
    expect(screen.getByText('Sales')).toBeInTheDocument()
    expect(screen.getByText('reads 1 dataset')).toBeInTheDocument()
  })

  it('renders ETL badges from extraction/transform/load fields', async () => {
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Orders')
    const eBadges = screen.getAllByText('E')
    expect(eBadges.length).toBe(2)
    expect(eBadges[0]).toHaveAttribute('title', 'Extracted from: query')
    expect(eBadges[1]).toHaveAttribute('title', 'Extracted from: csv')

    const tBadge = screen.getByText('T')
    expect(tBadge).toHaveAttribute('title', '2 active steps: filter_rows, sort')

    const lBadges = screen.getAllByText('L')
    expect(lBadges[0]).toHaveAttribute('title', expect.stringContaining('Refreshed'))
    expect(lBadges[0]).toHaveAttribute('title', expect.stringContaining('incremental'))
    expect(lBadges[1]).toHaveAttribute('title', 'Never refreshed')
  })
})

describe('Lineage empty columns', () => {
  it('says plainly when there are no datasets or reports yet, instead of a silent blank column', async () => {
    vi.mocked(lineageApi.graph).mockResolvedValue({
      sources: [{ id: 1, name: 'Warehouse', type: 'postgres' }],
      datasets: [],
      reports: [],
    })
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    expect(await screen.findByText('Warehouse')).toBeInTheDocument()
    expect(screen.getByText(/No datasets yet/)).toBeInTheDocument()
    expect(screen.getByText(/No reports yet/)).toBeInTheDocument()
  })
})

describe('the graph is operable without a mouse', () => {
  // "Click a node to trace its connections" is the whole point of this page,
  // and it was a bare <div onClick>: a keyboard user could read the graph but
  // never select anything in it.
  const nodeFor = (name: string) =>
    screen.getByRole('button', { name: new RegExp(name, 'i') })

  it('exposes each node as a focusable button', async () => {
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Warehouse')
    const node = nodeFor('Orders')
    expect(node).toHaveAttribute('tabIndex', '0')
    node.focus()
    expect(document.activeElement).toBe(node)
  })

  it('keeps the link that opens a node OUTSIDE the node button', async () => {
    // A link inside a role="button" is unreachable to a screen reader
    // (axe: nested-interactive); it sits beside the button in the same box.
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Warehouse')
    const node = nodeFor('Orders')
    expect(node.querySelector('a, button')).toBeNull()
    const open = screen.getByRole('link', { name: 'Open Orders' })
    expect(node.contains(open)).toBe(false)
    expect(node.parentElement?.contains(open)).toBe(true)
  })

  it('selects a node with Enter', async () => {
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Warehouse')
    const node = nodeFor('Orders')
    expect(node).toHaveAttribute('aria-pressed', 'false')
    fireEvent.keyDown(node, { key: 'Enter' })
    expect(nodeFor('Orders')).toHaveAttribute('aria-pressed', 'true')
  })

  it('selects a node with Space, which a real button also answers to', async () => {
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Warehouse')
    fireEvent.keyDown(nodeFor('Orders'), { key: ' ' })
    expect(nodeFor('Orders')).toHaveAttribute('aria-pressed', 'true')
  })

  it('deselects on a second press, matching the click behaviour', async () => {
    render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Warehouse')
    fireEvent.keyDown(nodeFor('Orders'), { key: 'Enter' })
    fireEvent.keyDown(nodeFor('Orders'), { key: 'Enter' })
    expect(nodeFor('Orders')).toHaveAttribute('aria-pressed', 'false')
  })
})


/**
 * Edge geometry must follow the reading direction.
 *
 * `dir="rtl"` mirrors the COLUMNS (they are flex children), but the connector
 * curves are SVG coordinates the browser knows nothing about. The original code
 * always drew from the source's RIGHT edge to the target's LEFT, which is only
 * correct while sources sit left of targets -- in RTL the curves swept off the
 * wrong side and stopped meeting the nodes they connect.
 *
 * jsdom reports every rect as zero (see jsdom-layout notes), so the nodes are
 * given real geometry here: without it every coordinate is 0 and the assertions
 * below would pass against a degenerate path regardless of direction.
 */
describe('Lineage edges mirror with the page direction', () => {
  /** Lay the three columns out left-to-right, or mirrored when `rtl`. */
  function stubLayout(rtl: boolean) {
    const COLUMN_X: Record<string, [number, number]> = rtl
      // mirrored: sources on the right, reports on the left
      ? { Warehouse: [700, 900], Orders: [400, 600], Customers: [400, 600], Sales: [100, 300] }
      : { Warehouse: [100, 300], Orders: [400, 600], Customers: [400, 600], Sales: [700, 900] }

    Element.prototype.getBoundingClientRect = function (this: Element) {
      const text = this.textContent ?? ''
      const hit = Object.keys(COLUMN_X).find(name => text.startsWith(name))
      // The container: the full canvas.
      if (!hit || text.includes('Warehouse') && text.includes('Sales')) {
        return { left: 0, right: 1000, top: 0, bottom: 600, width: 1000, height: 600, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
      }
      const [left, right] = COLUMN_X[hit]
      return { left, right, top: 100, bottom: 160, width: right - left, height: 60, x: left, y: 100, toJSON: () => ({}) } as DOMRect
    }
  }

  const originalRect = Element.prototype.getBoundingClientRect
  afterEach(() => { Element.prototype.getBoundingClientRect = originalRect })

  /** The x the first edge STARTS at, parsed out of its `M x y` command. */
  async function firstEdgeStartX(): Promise<number> {
    // The edges are painted by a requestAnimationFrame effect (see Lineage's
    // direction re-measure), so a node being on screen does NOT mean its edges
    // are. Reading straight after findByText raced that frame and failed about
    // one full-suite run in six, always on whichever test ran first.
    let path: Element | null = null
    await waitFor(() => {
      path = document.querySelector('svg path')
      expect(path, 'expected at least one edge to be drawn').not.toBeNull()
    })
    const d = path!.getAttribute('d') ?? ''
    const m = /^M ([\d.-]+) /.exec(d)
    expect(m, `unparseable path: ${d}`).not.toBeNull()
    return Number(m![1])
  }

  it('leaves the source box on its RIGHT in a left-to-right page', async () => {
    stubLayout(false)
    document.documentElement.dir = 'ltr'
    render(<DirectionProvider><MemoryRouter><Lineage /></MemoryRouter></DirectionProvider>)
    await screen.findByText('Orders')
    // Source column spans 100..300, so an edge out of it starts at its right edge.
    expect(await firstEdgeStartX()).toBe(300)
  })

  it('leaves the source box on its LEFT once the page is right-to-left', async () => {
    // THE regression. Before the fix this still read the right edge, so the
    // curve began on the far side of the node and crossed the whole canvas.
    stubLayout(true)
    document.documentElement.dir = 'rtl'
    localStorage.setItem('datalytics.direction', 'rtl')
    render(<DirectionProvider><MemoryRouter><Lineage /></MemoryRouter></DirectionProvider>)
    await screen.findByText('Orders')
    // Mirrored, the source column spans 700..900 and the edge leaves at 700.
    expect(await firstEdgeStartX()).toBe(700)
    localStorage.clear()
    document.documentElement.dir = 'ltr'
  })
})

describe('switching direction re-measures without a manual refresh', () => {
  /**
   * THE bug: the edges kept their old geometry until something else forced a
   * re-render, so a user had to refresh the page after switching to Arabic.
   *
   * Not a race -- a guaranteed ordering problem. `dir` is applied in
   * DirectionProvider's effect, and React runs a CHILD's effects BEFORE its
   * ancestors', so this page measured the columns before the browser had
   * mirrored them. The fix measures again on the next animation frame.
   */
  const originalRect = Element.prototype.getBoundingClientRect
  afterEach(() => { Element.prototype.getBoundingClientRect = originalRect })

  function layout(rtl: boolean) {
    const X: Record<string, [number, number]> = rtl
      ? { Warehouse: [700, 900], Orders: [400, 600], Customers: [400, 600], Sales: [100, 300] }
      : { Warehouse: [100, 300], Orders: [400, 600], Customers: [400, 600], Sales: [700, 900] }
    Element.prototype.getBoundingClientRect = function (this: Element) {
      const text = this.textContent ?? ''
      const hit = Object.keys(X).find(n => text.startsWith(n))
      if (!hit || (text.includes('Warehouse') && text.includes('Sales'))) {
        return { left: 0, right: 1000, top: 0, bottom: 600, width: 1000, height: 600, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
      }
      const [left, right] = X[hit]
      return { left, right, top: 100, bottom: 160, width: right - left, height: 60, x: left, y: 100, toJSON: () => ({}) } as DOMRect
    }
  }

  const firstEdgeStartX = () => {
    const d = document.querySelector('svg path')?.getAttribute('d') ?? ''
    return Number(/^M ([\d.-]+) /.exec(d)?.[1])
  }

  it('re-draws the edges when direction flips on a MOUNTED page', async () => {
    layout(false)
    localStorage.clear()
    const { rerender } = render(
      <DirectionProvider><MemoryRouter><Lineage /></MemoryRouter></DirectionProvider>)
    await screen.findByText('Orders')
    // waitFor, not a bare assertion: the edges are painted by a
    // requestAnimationFrame effect, so a node being on screen does not mean
    // its edges are. Reading straight after findByText raced that frame and
    // failed as `expected NaN to be 300` about one full-suite run in five --
    // the same trap the other block's helper already guards against.
    // The timeout is not decoration. waitFor's default is one second, and the
    // re-measure is two rAF frames behind a re-render; under a full-suite run
    // that window closes late often enough to fail as "expected 300 to be 700"
    // while passing every time the file runs alone. A longer wait cannot make a
    // broken re-measure pass -- it never arrives at all -- so patience here
    // costs nothing and removes a failure that looks like an RTL regression.
    await waitFor(() => expect(firstEdgeStartX()).toBe(300), { timeout: 8000 })  // LTR: leaves the source's right

    // The mirrored layout arrives, exactly as it does when the user toggles.
    layout(true)
    localStorage.setItem('datalytics.direction', 'rtl')
    rerender(
      <DirectionProvider><MemoryRouter><Lineage /></MemoryRouter></DirectionProvider>)

    // Without the rAF re-measure this stays 300 -- the stale value the user
    // had to refresh away.
    await waitFor(() => expect(firstEdgeStartX()).toBe(700), { timeout: 8000 })
    localStorage.clear()
    // vitest caps a test at 5s by default, so a waitFor allowed longer than
    // that never gets to finish -- the run fails as "Test timed out" instead,
    // which looks like a hang rather than the slow frame it is.
  }, 20000)
})

describe('Lineage accessibility', () => {
  it('has no structural accessibility violations', async () => {
    const { container } = render(<MemoryRouter><Lineage /></MemoryRouter>)
    await screen.findByText('Warehouse')
    expect(await axeViolations(container)).toEqual([])
  })
})
