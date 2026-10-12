import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Lineage from './Lineage'
import { DirectionProvider } from '../contexts/DirectionContext'
import { lineageApi, type LineageGraph } from '../services/api'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({ lineageApi: { graph: vi.fn() } }))

/** Step 11: the Lineage explorer, Part A -- the graph, cards, edges, toolbar,
 *  search, filters, issues only, pan / zoom / fit and the mini-map. */

const load = (over: Partial<Record<string, unknown>> = {}) => ({
  last_refreshed_at: new Date(Date.now() - 2 * 3600_000).toISOString(), strategy: 'full', cursor_column: null, staleness: 'fresh', ...over,
}) as LineageGraph['datasets'][number]['load']
const GRAPH: LineageGraph = {
  sources: [{ id: 1, name: 'Warehouse', type: 'postgresql' }],
  datasets: [
    { id: 5, name: 'Orders', mode: 'import', source_id: 1, joins: [6], extraction_kind: 'query', transform: { count: 2, kinds: ['filter_rows', 'sort'] }, load: load() },
    { id: 6, name: 'Customers', mode: 'import', source_id: null, joins: [], extraction_kind: 'csv', transform: { count: 0, kinds: [] }, load: load({ staleness: 'never', last_refreshed_at: null }) },
    { id: 7, name: 'Live stock', mode: 'directquery', source_id: 1, joins: [], extraction_kind: 'query', transform: { count: 0, kinds: [] }, load: load(), health: 'failing' },
    { id: 8, name: 'Spare', mode: 'import', source_id: 1, joins: [], extraction_kind: 'query', transform: { count: 0, kinds: [] }, load: load() },
  ],
  reports: [{ id: 9, name: 'Sales', dataset_ids: [5] }, { id: 10, name: 'Stock board', dataset_ids: [7] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(lineageApi.graph).mockResolvedValue(structuredClone(GRAPH))
})

const page = () => render(<MemoryRouter><DirectionProvider><Lineage /></DirectionProvider></MemoryRouter>)
const card = (name: string) => screen.getByRole('button', { name: new RegExp(`^${name},`) })
const cls = (name: string) => card(name).className

describe('the graph', () => {
  it('draws sources, datasets and reports as cards, with uploads as their own source', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    for (const n of ['Warehouse', 'Uploaded files', 'Orders', 'Customers', 'Live stock', 'Spare', 'Sales', 'Stock board']) expect(card(n)).toBeInTheDocument()
    expect(card('Orders')).toHaveTextContent('Import')
    expect(card('Orders')).toHaveTextContent('2 steps')
    expect(card('Live stock')).toHaveTextContent('DirectQuery')
    expect(card('Warehouse')).toHaveTextContent('PostgreSQL')
    expect(card('Sales')).toHaveTextContent('reads 1 dataset')
    expect(card('Orders')).toHaveAccessibleName('Orders, Dataset. Feeds from 2, used by 1.')
  })

  it('draws an edge per flow: extract, join (dashed) and reads; red out of a failing dataset', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: /^Orders,/ })
    const edge = (from: string, to: string) => container.querySelector(`g[data-from="${from}"][data-to="${to}"]`)
    expect(edge('src:1', 'ds:5')).toHaveClass('dl-ln-e--extract')
    expect(edge('src:upload', 'ds:6')).toHaveClass('dl-ln-e--extract')
    expect(edge('ds:6', 'ds:5')).toHaveClass('dl-ln-e--join')
    expect(edge('ds:5', 'rep:9')).toHaveClass('dl-ln-e--reads')
    expect(edge('ds:7', 'rep:10')).toHaveClass('is-bad')
    expect(edge('ds:5', 'rep:9')).not.toHaveClass('is-bad')
  })

  it('marks issues: a failing refresh, a report reading it, and a dataset nothing uses', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    expect(card('Live stock').querySelector('.dl-ln-iss--fail')).toHaveAttribute('title', 'Refresh failing')
    expect(card('Stock board').querySelector('.dl-ln-iss--broken')).toHaveAttribute('title', 'Uses data whose refresh is failing')
    expect(card('Spare').querySelector('.dl-ln-iss--orphan')).toHaveAttribute('title', 'No reports use it')
    expect(card('Orders').querySelector('.dl-ln-iss')).toBeNull()
    expect(screen.getByRole('button', { name: /Show issues only/ })).toHaveTextContent('3')
  })

  it('a click lights the whole path and fades the rest; a second click clears it', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    fireEvent.click(card('Orders'))
    expect(card('Orders')).toHaveAttribute('aria-pressed', 'true')
    for (const n of ['Warehouse', 'Customers', 'Uploaded files', 'Sales']) expect(cls(n)).toContain('is-on')
    for (const n of ['Live stock', 'Spare', 'Stock board']) expect(cls(n)).toContain('is-dim')
    fireEvent.click(card('Orders'))
    expect(cls('Spare')).not.toContain('is-dim')
  })

  it('folds a long column into "+ N more", and opens it', async () => {
    const many = structuredClone(GRAPH)
    for (let i = 0; i < 12; i++) many.reports.push({ id: 100 + i, name: `Board ${i}`, dataset_ids: [5] })
    vi.mocked(lineageApi.graph).mockResolvedValue(many)
    page()
    const more = await screen.findByRole('button', { name: '+ 4 more reports' })
    fireEvent.click(more)
    expect(screen.getByRole('button', { name: 'Show fewer' })).toBeInTheDocument()
    expect(card('Board 11')).toBeInTheDocument()
  })
})

describe('the toolbar', () => {
  it('search lists matches; picking one makes it pulse', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    const box = screen.getByRole('combobox', { name: 'Find a source, dataset or report…' })
    fireEvent.change(box, { target: { value: 'stock' } })
    const list = screen.getByRole('listbox')
    expect(within(list).getAllByRole('option').map(o => o.textContent)).toEqual(['Live stockDataset', 'Stock boardReport'])
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(cls('Stock board')).toContain('is-hit')
    fireEvent.change(box, { target: { value: 'zzz' } })
    expect(screen.getByText('No matches')).toBeInTheDocument()
  })

  it('filters fade what fails them and move nothing', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    const top = card('Spare').style.top
    fireEvent.click(screen.getByRole('button', { name: /Show issues only/ }))
    expect(cls('Orders')).toContain('is-dim')
    expect(cls('Live stock')).not.toContain('is-dim')
    expect(cls('Spare')).not.toContain('is-dim')
    expect(card('Spare').style.top).toBe(top)
    fireEvent.click(screen.getByRole('button', { name: /Show issues only/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Mode' }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'DirectQuery' }))
    expect(cls('Live stock')).not.toContain('is-dim')
    expect(cls('Stock board')).not.toContain('is-dim')
    expect(cls('Orders')).toContain('is-dim')
    expect(screen.getByRole('button', { name: 'DirectQuery' })).toHaveClass('is-on')
  })

  it('node type is a multi-choice menu worked by keyboard', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    fireEvent.click(screen.getByRole('button', { name: 'Node type' }))
    const menu = screen.getByRole('menu', { name: 'Node type' })
    const [src] = within(menu).getAllByRole('menuitemcheckbox')
    expect(src).toHaveFocus()
    fireEvent.click(src)
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(src).toHaveAttribute('aria-checked', 'true')
    fireEvent.keyDown(menu, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    expect(cls('Orders')).toContain('is-dim')
    expect(cls('Warehouse')).not.toContain('is-dim')
  })

  it('source type lists the types there are, by their usual names', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    fireEvent.click(screen.getByRole('button', { name: 'Source type' }))
    expect(screen.getAllByRole('menuitemradio').map(o => o.textContent)).toEqual(['PostgreSQL', 'File'])
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'File' }))
    expect(cls('Customers')).not.toContain('is-dim')
    expect(cls('Orders')).toContain('is-dim')
  })
})

describe('pan, zoom and the mini-map', () => {
  it('zooms with the buttons and the wheel, and fits back', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    const pct = () => screen.getByTestId('zoom-pct').textContent
    const start = pct()
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(pct()).not.toBe(start)
    fireEvent.click(screen.getByRole('button', { name: 'Fit to screen' }))
    expect(pct()).toBe(start)
    fireEvent.wheel(screen.getByRole('region', { name: /Lineage graph/ }), { deltaY: -100 })
    expect(pct()).not.toBe(start)
  })

  it('drags the background to pan', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    const world = screen.getByTestId('lineage-world')
    const before = world.style.transform
    const cv = screen.getByRole('region', { name: /Lineage graph/ })
    // jsdom has no PointerEvent: mouse events carrying the pointer's fields.
    const ptr = (type: string, x: number, y: number) => fireEvent(cv, Object.assign(
      new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 }), { pointerId: 1 }))
    ptr('pointerdown', 100, 100); ptr('pointermove', 160, 130); ptr('pointerup', 160, 130)
    expect(world.style.transform).not.toBe(before)
  })

  it('draws every visible card in the mini-map', async () => {
    page()
    await screen.findByRole('button', { name: /^Orders,/ })
    expect(screen.getByRole('img', { name: /Mini-map/ }).querySelectorAll('rect:not(.dl-ln-mini__vp)')).toHaveLength(8)
  })
})

describe('direction and accessibility', () => {
  it('mirrors the flow in Arabic: sources on the right', async () => {
    localStorage.setItem('datalytics.direction', 'rtl')
    try {
      page()
      await screen.findByRole('button', { name: /^Orders/ })
      const left = (k: string) => parseFloat((document.querySelector(`[data-key="${k}"]`) as HTMLElement).style.left)
      expect(left('src:1')).toBeGreaterThan(left('ds:5'))
      expect(left('ds:5')).toBeGreaterThan(left('rep:9'))
    } finally { localStorage.removeItem('datalytics.direction') }
  })

  it('says plainly when the graph could not be loaded', async () => {
    vi.mocked(lineageApi.graph).mockRejectedValue(new Error('down'))
    page()
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Lineage graph/ })).toBeNull()
  })

  it('has no structural accessibility violations', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: /^Orders,/ })
    await waitFor(async () => expect(await axeViolations(container)).toEqual([]))
  })
})
