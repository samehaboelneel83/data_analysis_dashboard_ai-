import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import TemplatesPane from './TemplatesPane'
import { pageTemplatesApi, reportsApi } from '../../services/api'

/** Redesign 7e2: the left panel's Templates tab. */

vi.mock('../../services/api', async orig => ({
  ...(await orig<Record<string, unknown>>()),
  pageTemplatesApi: { builtins: vi.fn(), list: vi.fn(), addFrom: vi.fn(), saveFrom: vi.fn(), delete: vi.fn() },
  reportsApi: { list: vi.fn(), get: vi.fn() },
}))

beforeEach(() => {
  vi.mocked(pageTemplatesApi.builtins).mockResolvedValue([{ key: 'kpi-strip', name: 'KPI overview', widgets: 6 }, { key: 'quad', name: 'Four-panel comparison', widgets: 4 }])
  vi.mocked(pageTemplatesApi.list).mockResolvedValue([{ id: 7, name: 'Quarterly layout', widgets: 5 }])
  vi.mocked(pageTemplatesApi.addFrom).mockResolvedValue({ page_id: 9, widgets: 6 })
  vi.mocked(pageTemplatesApi.saveFrom).mockResolvedValue({})
  vi.mocked(pageTemplatesApi.delete).mockResolvedValue(undefined as never)
  vi.mocked(reportsApi.list).mockResolvedValue([])
})

describe('Templates tab (7e2)', () => {
  it('lists the built-in page layouts as cards; Add page adds one', async () => {
    const onAdded = vi.fn()
    render(<TemplatesPane reportId={1} activePageId={100} onAdded={onAdded} />)
    const card = (await screen.findByText('KPI overview')).closest('article') as HTMLElement
    expect(card).toHaveTextContent('6 widgets')
    fireEvent.click(screen.getAllByRole('button', { name: /Add page/ })[0])
    await waitFor(() => expect(pageTemplatesApi.addFrom).toHaveBeenCalledWith(1, { builtin: 'kpi-strip' }))
    await waitFor(() => expect(onAdded).toHaveBeenCalled())
  })

  it('lists your saved page templates, and deletes one after asking', async () => {
    render(<TemplatesPane reportId={1} activePageId={100} onAdded={vi.fn()} />)
    expect(await screen.findByText('Quarterly layout')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete template Quarterly layout' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(pageTemplatesApi.delete).toHaveBeenCalledWith(7))
    await waitFor(() => expect(screen.queryByText('Quarterly layout')).toBeNull())
  })

  it('saves the open page as a template', async () => {
    render(<TemplatesPane reportId={1} activePageId={100} onAdded={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Save this page as a template' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'New template name' }), { target: { value: 'Board pack' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save page template' }))
    await waitFor(() => expect(pageTemplatesApi.saveFrom).toHaveBeenCalledWith(1, 100, 'Board pack'))
  })

  it('shows v1 widget templates below, as passed in', async () => {
    render(<TemplatesPane reportId={1} activePageId={100} onAdded={vi.fn()} widgetTemplates={<p>widget templates here</p>} />)
    expect(await screen.findByText('widget templates here')).toBeInTheDocument()
  })
})
