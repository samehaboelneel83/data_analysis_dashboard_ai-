import { describe, it, expect, vi, beforeEach } from 'vitest'
import { withMeasuredTiles } from '../test/measuredTiles'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import EmbeddedReport from './EmbeddedReport'
import { embedApi } from '../services/api'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({
  embedApi: { report: vi.fn(), widgetData: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]) },
}))

const payload = {
  name: 'Quarterly', theme: 'default', dataset_id: 5, column_formats: {}, calculated_columns: [],
  embed_session_token: 'session-tok',
  pages: [{ id: 1, name: 'P1', page_type: 'normal', position: 0,
    widgets: [{ id: 9, page_id: 1, widget_type: 'bar', title: 'Rev', config: { dimension: 'r' }, layout: { x: 0, y: 0, w: 6, h: 4 } }] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(embedApi.report).mockResolvedValue(payload)
  vi.mocked(embedApi.widgetData).mockResolvedValue({ rows: [{ name: 'US', value: 10 }], total: 1 })
})

function mount(search = '?token=host-jwt') {
  return render(
    <MemoryRouter initialEntries={[`/embed${search}`]}>
      <Routes><Route path="/embed" element={<EmbeddedReport />} /></Routes>
    </MemoryRouter>
  )
}

describe('EmbeddedReport', () => {
  it('renders the report from the embed payload and fetches widget data with the session token', async () => {
    mount()
    expect(await screen.findByText('Quarterly')).toBeInTheDocument()
    expect(screen.getByText(/Embedded view/)).toBeInTheDocument()
    await waitFor(() => expect(embedApi.widgetData).toHaveBeenCalledWith('session-tok', 9))
  })

  it('never calls widget-data with the original host token', async () => {
    mount()
    await screen.findByText('Quarterly')
    expect(embedApi.widgetData).not.toHaveBeenCalledWith('host-jwt', 9)
  })

  it('shows an error state for a missing token', async () => {
    mount('')
    expect(await screen.findByText(/missing its token/)).toBeInTheDocument()
    expect(embedApi.report).not.toHaveBeenCalled()
  })

  it('shows an error state for an invalid/expired/disallowed embed link', async () => {
    vi.mocked(embedApi.report).mockRejectedValue(new Error('401'))
    mount()
    expect(await screen.findByText(/invalid, expired, or not allowed/)).toBeInTheDocument()
  })

  it('never shows a tab for a non-normal page', async () => {
    vi.mocked(embedApi.report).mockResolvedValue({
      ...payload,
      pages: [...payload.pages, { id: 2, name: 'Working Notes', page_type: 'hidden', position: 1, widgets: [] }],
    })
    mount()
    await screen.findByText('Quarterly')
    expect(screen.queryByText('Working Notes')).not.toBeInTheDocument()
  })

  it('surfaces a rate-limited state for a 429 widget and can retry', async () => {
    vi.mocked(embedApi.widgetData).mockRejectedValueOnce({ response: { status: 429 } })
    mount()
    expect(await screen.findByText(/Temporarily rate-limited/)).toBeInTheDocument()
    vi.mocked(embedApi.widgetData).mockResolvedValueOnce({ rows: [{ name: 'US', value: 10 }], total: 1 })
    screen.getByRole('button', { name: 'Try again' }).click()
    await waitFor(() => expect(screen.queryByText(/Temporarily rate-limited/)).not.toBeInTheDocument())
  })
})

/**
 * What an embedded viewer can see and undo.
 *
 * The embed mounted `CrossFilterProvider` with NO props. Three things followed
 * from that, and all three are wrong for the surface where they matter most:
 *
 *   1. `widgets` was absent, so `storedInteractions` hydrated nothing -- a
 *      widget the author set to "isolated" broadcast anyway, because the
 *      provider's default is `broadcasts ?? true`. The author's setting simply
 *      did not survive publication.
 *   2. No FilterBar, so a viewer who clicked a region had no way to see what
 *      was filtering or to clear it, and no other UI to fall back on. An
 *      author at least has the Actions pane.
 *
 * The builder passes all of this; the embed is where a stranger meets the
 * report, so it is the surface that can least afford to get it wrong.
 */
describe('the embedded viewer can see and clear its filters', () => {
  withMeasuredTiles()
  const mapPayload = (interaction?: unknown) => ({
    ...payload,
    pages: [{ id: 1, name: 'P1', page_type: 'normal', position: 0,
      widgets: [{ id: 31, page_id: 1, widget_type: 'map_choropleth', title: 'Sales',
        config: { dimension: 'country', measure: 'revenue', ...(interaction ? { interaction } : {}) },
        layout: { x: 0, y: 0, w: 6, h: 4 } }] }],
  })

  /** The map renderers are lazy and pull the world atlas with them, which takes
   *  several seconds here -- well past waitFor's default second. */
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
    vi.mocked(embedApi.report).mockResolvedValue(mapPayload())
    vi.mocked(embedApi.widgetData).mockResolvedValue({ rows: [{ name: 'France', value: 3 }], total: 1 })
    const { container } = mount()
    await screen.findByText('Quarterly')

    fireEvent.click(await findRegion(container, 'France'))
    await waitFor(() => expect(screen.getByText(/country = France/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /remove filter country = France/i }))
    expect(screen.getByText(/no selections/i)).toBeInTheDocument()
  }, 30000)

  it("honours a widget the author published as isolated", async () => {
    // config.interaction is in the embed payload already; only the provider
    // was never handed the widgets to read it from.
    vi.mocked(embedApi.report).mockResolvedValue(
      mapPayload({ broadcasts: false, receives: true }))
    vi.mocked(embedApi.widgetData).mockResolvedValue({ rows: [{ name: 'France', value: 3 }], total: 1 })
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
    vi.mocked(embedApi.report).mockResolvedValue({
      ...mapPayload({ broadcasts: false, receives: true }),
      pages: [{ ...mapPayload({ broadcasts: false, receives: true }).pages[0],
        interaction_mode: 'twoway' }],
    })
    vi.mocked(embedApi.widgetData).mockResolvedValue({ rows: [{ name: 'France', value: 3 }], total: 1 })
    const { container } = mount()
    await screen.findByText('Quarterly')

    fireEvent.click(await findRegion(container, 'France'))
    await waitFor(() => expect(screen.getByText(/country = France/)).toBeInTheDocument())
  }, 30000)
})

describe('EmbeddedReport accessibility', () => {
  it('has no structural accessibility violations', async () => {
    const { container } = mount()
    await screen.findByText('Quarterly')
    expect(await axeViolations(container)).toEqual([])
  })
})
