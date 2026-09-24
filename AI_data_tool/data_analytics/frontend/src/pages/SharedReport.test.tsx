import { describe, it, expect, vi, beforeEach } from 'vitest'
import { withMeasuredTiles } from '../test/measuredTiles'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import SharedReport from './SharedReport'
import { sharedApi } from '../services/api'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({
  sharedApi: { report: vi.fn(), widgetData: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]) },
}))

const payload = {
  name: 'Quarterly', theme: 'default', dataset_id: 5, column_formats: {}, calculated_columns: [],
  pages: [{ id: 1, name: 'P1', page_type: 'normal', position: 0,
    widgets: [{ id: 9, page_id: 1, widget_type: 'bar', title: 'Rev', config: { dimension: 'r' }, layout: { x: 0, y: 0, w: 6, h: 4 } }] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(sharedApi.report).mockResolvedValue(payload)
  vi.mocked(sharedApi.widgetData).mockResolvedValue({ rows: [{ name: 'US', value: 10 }], total: 1 })
})

function mount() {
  return render(
    <MemoryRouter initialEntries={['/shared/tok']}>
      <Routes><Route path="/shared/:token" element={<SharedReport />} /></Routes>
    </MemoryRouter>
  )
}

describe('SharedReport', () => {
  it('renders the report read-only from the shared payload and per-widget data', async () => {
    mount()
    expect(await screen.findByText('Quarterly')).toBeInTheDocument()
    expect(screen.getByText(/read only/)).toBeInTheDocument()
    await waitFor(() => expect(sharedApi.widgetData).toHaveBeenCalledWith('tok', 9))
  })

  it('shows the expiry message for a dead link', async () => {
    vi.mocked(sharedApi.report).mockRejectedValue(new Error('404'))
    mount()
    expect(await screen.findByText(/does not exist or has expired/)).toBeInTheDocument()
  })

  it('never shows a tab for a non-normal page, even if the payload somehow carries one', async () => {
    vi.mocked(sharedApi.report).mockResolvedValue({
      ...payload,
      pages: [
        ...payload.pages,
        { id: 2, name: 'Working Notes', page_type: 'hidden', position: 1, widgets: [] },
        { id: 3, name: 'A Popup', page_type: 'popup', position: 2, widgets: [] },
      ],
    })
    mount()
    await screen.findByText('Quarterly')
    expect(screen.queryByText('Working Notes')).not.toBeInTheDocument()
    expect(screen.queryByText('A Popup')).not.toBeInTheDocument()
  })

  it('labels a pinned link\'s layout', async () => {
    vi.mocked(sharedApi.report).mockResolvedValue({ ...payload, pinned: true })
    mount()
    expect(await screen.findByText('Layout pinned at share time')).toBeInTheDocument()
  })

  it('does not label an unpinned link', async () => {
    mount()
    await screen.findByText('Quarterly')
    expect(screen.queryByText('Layout pinned at share time')).not.toBeInTheDocument()
  })

  it('surfaces a rate-limited state for a 429 widget instead of rendering it blank', async () => {
    vi.mocked(sharedApi.widgetData).mockRejectedValue({ response: { status: 429 } })
    mount()
    expect(await screen.findByText(/Temporarily rate-limited/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('retries a rate-limited widget and renders it once the retry succeeds', async () => {
    vi.mocked(sharedApi.widgetData).mockRejectedValueOnce({ response: { status: 429 } })
    mount()
    await screen.findByText(/Temporarily rate-limited/)
    vi.mocked(sharedApi.widgetData).mockResolvedValueOnce({ rows: [{ name: 'US', value: 10 }], total: 1 })
    screen.getByRole('button', { name: 'Try again' }).click()
    await waitFor(() => expect(screen.queryByText(/Temporarily rate-limited/)).not.toBeInTheDocument())
  })

  it('still shows a genuinely empty widget as empty, not rate-limited', async () => {
    vi.mocked(sharedApi.widgetData).mockRejectedValue(new Error('no data'))
    mount()
    await screen.findByText('Quarterly')
    expect(screen.queryByText(/Temporarily rate-limited/)).not.toBeInTheDocument()
  })
})

/**
 * The same two defects the embed had, on the surface a report is most often
 * handed to someone through: a share link.
 *
 * The provider was mounted with no props, so saved per-widget interactions
 * never hydrated (a widget published as isolated broadcast anyway), and there
 * was no filter strip -- a recipient who clicked a region could see neither
 * what they had filtered nor how to undo it.
 */
describe('a share-link recipient can see and clear their filters', () => {
  withMeasuredTiles()
  const mapPayload = (interaction?: unknown) => ({
    ...payload,
    pages: [{ id: 1, name: 'P1', page_type: 'normal', position: 0,
      widgets: [{ id: 31, page_id: 1, widget_type: 'map_choropleth', title: 'Sales',
        config: { dimension: 'country', measure: 'revenue', ...(interaction ? { interaction } : {}) },
        layout: { x: 0, y: 0, w: 6, h: 4 } }] }],
  })

  /** The lazy map chunk pulls the world atlas with it -- seconds, not the one
   *  waitFor allows by default. */
  const findRegion = (container: HTMLElement, label: string) =>
    waitFor(() => {
      const el = container.querySelector(`[data-country="${label}"]`)
      expect(el).not.toBeNull()
      return el as Element
    }, { timeout: 20000 })

  it('shows the filter strip before anything is filtering', async () => {
    mount()
    await screen.findByText('Quarterly')
    expect(screen.getByText(/no selections/i)).toBeInTheDocument()
  })

  it('names the filter a region click applied, and clears it', async () => {
    vi.mocked(sharedApi.report).mockResolvedValue(mapPayload())
    vi.mocked(sharedApi.widgetData).mockResolvedValue({ rows: [{ name: 'France', value: 3 }], total: 1 })
    const { container } = mount()
    await screen.findByText('Quarterly')

    fireEvent.click(await findRegion(container, 'France'))
    await waitFor(() => expect(screen.getByText(/country = France/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /remove filter country = France/i }))
    expect(screen.getByText(/no selections/i)).toBeInTheDocument()
  }, 30000)

  it('honours a widget the author published as isolated', async () => {
    vi.mocked(sharedApi.report).mockResolvedValue(
      mapPayload({ broadcasts: false, receives: true }))
    vi.mocked(sharedApi.widgetData).mockResolvedValue({ rows: [{ name: 'France', value: 3 }], total: 1 })
    const { container } = mount()
    await screen.findByText('Quarterly')

    fireEvent.click(await findRegion(container, 'France'))
    await waitFor(() => expect(screen.getByText(/no selections/i)).toBeInTheDocument())
    expect(screen.queryByText(/country = France/)).not.toBeInTheDocument()
  }, 30000)

  it("lets the page's authored mode override a widget's own setting", async () => {
    // The page-level modes are documented as mutually exclusive with manual
    // per-widget actions: under any automatic mode EVERY widget broadcasts.
    // The viewer never received the mode, so a page authored as twoway
    // behaved as manual -- the isolated widget above stayed silent when the
    // author's page setting says it should not.
    vi.mocked(sharedApi.report).mockResolvedValue({
      ...mapPayload({ broadcasts: false, receives: true }),
      pages: [{ ...mapPayload({ broadcasts: false, receives: true }).pages[0],
        interaction_mode: 'twoway' }],
    })
    vi.mocked(sharedApi.widgetData).mockResolvedValue({ rows: [{ name: 'France', value: 3 }], total: 1 })
    const { container } = mount()
    await screen.findByText('Quarterly')

    fireEvent.click(await findRegion(container, 'France'))
    await waitFor(() => expect(screen.getByText(/country = France/)).toBeInTheDocument())
  }, 30000)
})

describe('SharedReport on a phone', () => {
  it('stacks widgets in reading order and turns pages with a swipe', async () => {
    const mm = window.matchMedia
    window.matchMedia = ((q: string) => ({ matches: q.includes('max-width'), media: q, addEventListener: () => {},
      removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false })) as never
    try {
      vi.mocked(sharedApi.report).mockResolvedValue({
        ...payload,
        pages: [
          { id: 1, name: 'P1', page_type: 'normal', position: 0, widgets: [
            { id: 9, page_id: 1, widget_type: 'bar', title: 'Right', config: { dimension: 'r' }, layout: { x: 6, y: 0, w: 6, h: 4 } },
            { id: 8, page_id: 1, widget_type: 'bar', title: 'Left', config: { dimension: 'r' }, layout: { x: 0, y: 0, w: 6, h: 4 } },
          ] },
          { id: 2, name: 'P2', page_type: 'normal', position: 1, widgets: [
            { id: 7, page_id: 2, widget_type: 'bar', title: 'Second page', config: { dimension: 'r' }, layout: { x: 0, y: 0, w: 12, h: 4 } },
          ] },
        ],
      })
      mount()
      const pageEl = await screen.findByTestId('shared-page')
      await screen.findByText('Left')
      const text = pageEl.textContent ?? ''
      expect(text.indexOf('Left')).toBeLessThan(text.indexOf('Right'))
      expect(pageEl.style.display).toBe('flex')
      fireEvent.touchStart(pageEl, { touches: [{ clientX: 300 }] })
      fireEvent.touchEnd(pageEl, { changedTouches: [{ clientX: 100 }] })
      expect(await screen.findByText('Second page')).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'P2' }).getAttribute('aria-selected')).toBe('true')
    } finally {
      window.matchMedia = mm
    }
  })
})

describe('SharedReport accessibility', () => {
  it('has no structural accessibility violations for a reader', async () => {
    const { container } = mount()
    await screen.findByText('Quarterly')
    await waitFor(() => expect(sharedApi.widgetData).toHaveBeenCalled())
    expect(await axeViolations(container)).toEqual([])
  })
})
