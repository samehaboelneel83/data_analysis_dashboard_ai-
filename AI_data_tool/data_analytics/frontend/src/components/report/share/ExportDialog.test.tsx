import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../../test/renderWithProviders'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ExportDialog from './ExportDialog'
import { authzApi, reportsApi } from '../../../services/api'

/**
 * The Export dialog (redesign 7c). Pinned: the PDF options reach the server
 * exactly (v1's PdfOptionsDialog behaviour), zero pages cannot be exported,
 * the export policy greys downloads with its reason, and a failure shows the
 * server's own words with a retry.
 */

vi.mock('../../../services/api', () => ({
  authzApi: { decisions: vi.fn() },
  reportsApi: { downloadPdf: vi.fn(), downloadXlsx: vi.fn(), downloadPackage: vi.fn() },
}))

const page = (id: number, name: string) => ({ id, name, page_type: 'normal', widgets: [] })
const report = { id: 3, name: 'Sales', pages: [page(1, 'Overview'), page(2, 'Regions')] } as never

const open = () => render(
  <MemoryRouter>
    <Routes>
      <Route path="/" element={<ExportDialog report={report} onClose={() => {}} />} />
      <Route path="/reports/:id/print" element={<div data-testid="print-view" />} />
    </Routes>
  </MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(authzApi.decisions).mockResolvedValue([{ resource: 'report', id: 3, action: 'download', allowed: true, reason: '' }] as never)
  vi.mocked(reportsApi.downloadPdf).mockResolvedValue(undefined as never)
})

describe('ExportDialog', () => {
  it('hands back paper, orientation, contents and the chosen pages', async () => {
    open()
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Letter' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Portrait' }))
    fireEvent.click(within(dialog).getByLabelText('Contents page'))
    fireEvent.click(within(dialog).getByRole('button', { name: /Regions/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Export PDF' }))
    await waitFor(() => expect(reportsApi.downloadPdf).toHaveBeenCalledWith(3, 'Sales',
      { paper: 'Letter', orientation: 'portrait', contents: false, pages: [1] }))
    expect(await screen.findByText('Your file is ready')).toBeInTheDocument()
  })

  it('will not export zero pages', async () => {
    open()
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /Overview/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: /Regions/ }))
    expect(within(dialog).getByRole('button', { name: 'Export PDF' })).toBeDisabled()
    expect(within(dialog).getByText('Choose at least one page.')).toBeInTheDocument()
  })

  it('exports the Excel workbook and says how many sheets, and what was withheld', async () => {
    vi.mocked(reportsApi.downloadXlsx).mockResolvedValue({ sheets: 4, withheld: 1 } as never)
    open()
    fireEvent.click(await screen.findByRole('radio', { name: /Data \(Excel\)/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Export data' }))
    await waitFor(() => expect(reportsApi.downloadXlsx).toHaveBeenCalledWith(3, 'Sales'))
    expect(await screen.findByRole('status')).toHaveTextContent(/4/)
  })

  it("a failure shows the server's reason and can be retried", async () => {
    vi.mocked(reportsApi.downloadPdf).mockRejectedValueOnce({ response: { data: new Blob([JSON.stringify({ detail: 'Chromium is not installed' })]) } })
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Export PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Chromium is not installed')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(reportsApi.downloadPdf).toHaveBeenCalledTimes(2))
  })

  it('the export policy greys every download with its reason, and Print still works', async () => {
    vi.mocked(authzApi.decisions).mockResolvedValue([{ resource: 'report', id: 3, action: 'download', allowed: false,
      reason: 'Restricted data cannot be downloaded.' }] as never)
    open()
    const pdf = await screen.findByRole('radio', { name: /PDF/ })
    await waitFor(() => expect(pdf).toBeDisabled())
    expect(screen.getByRole('note')).toHaveTextContent('Restricted data cannot be downloaded.')
    fireEvent.click(screen.getByRole('button', { name: 'Open print view' }))
    expect(await screen.findByTestId('print-view')).toBeInTheDocument()
  })
})
