import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ReportPrint from './ReportPrint'
import { reportsApi } from '../services/api'

vi.mock('../services/api', () => ({
  reportsApi: { get: vi.fn() },
  datasetsApi: { get: vi.fn() },
}))

function renderAt(id = 1) {
  return render(
    <MemoryRouter initialEntries={[`/reports/${id}/print`]}>
      <Routes><Route path="/reports/:id/print" element={<ReportPrint />} /></Routes>
    </MemoryRouter>
  )
}

describe('ReportPrint loading and error states', () => {
  beforeEach(() => { vi.mocked(reportsApi.get).mockReset() })

  it('shows the shared loading state before the report arrives', () => {
    vi.mocked(reportsApi.get).mockReturnValue(new Promise(() => {}))
    renderAt()
    expect(screen.getByText('Preparing print view…')).toBeInTheDocument()
  })

  it('shows a retry-capable error banner, not a bare error string, when the report fails to load', async () => {
    vi.mocked(reportsApi.get).mockRejectedValue({ response: { data: { detail: 'Report not found' } } })
    renderAt()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/could not load/i)).toBeInTheDocument()
    expect(screen.getByText('Report not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('retries the load when "Try again" is clicked', async () => {
    vi.mocked(reportsApi.get)
      .mockRejectedValueOnce({ response: { data: { detail: 'Report not found' } } })
      .mockResolvedValueOnce({ id: 1, name: 'Sales', dataset_id: null, pages: [] } as any)
    renderAt()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    screen.getByRole('button', { name: /try again/i }).click()

    await waitFor(() => expect(screen.getByText('Sales')).toBeInTheDocument())
    expect(reportsApi.get).toHaveBeenCalledTimes(2)
  })
})

describe('the print view (QA2 Visual 7, Translation 15)', () => {
  const report = { id: 1, name: 'Sales', dataset_id: null, pages: [{ id: 10, name: 'P1', page_type: 'normal', widgets: [] }, { id: 11, name: 'P2', page_type: 'normal', widgets: [] }] }

  it('is paper: its own light theme, whatever the app\'s theme', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(report as never)
    const { container } = renderAt()
    await screen.findByRole('heading', { name: 'Sales' })
    const paper = container.querySelector('.dl-paper')!
    expect(paper).toHaveAttribute('data-product', 'datalytics')
    expect(paper).toHaveAttribute('data-theme', 'light')
    // The bridge tokens re-resolve on such a subtree, or it would keep the
    // dark values computed on <html>.
    const fs = await import('node:fs'); const path = await import('node:path')
    const css = fs.readFileSync(path.join(__dirname, '..', 'index.css'), 'utf8')
    expect(css).toMatch(/:root, \[data-product="datalytics"\] \{\s*--bg:/)
  })

  it('turns the whole page light while it is open, and gives the reader\'s theme back', async () => {
    localStorage.setItem('theme', 'dark'); document.documentElement.setAttribute('data-theme', 'dark')
    try {
      vi.mocked(reportsApi.get).mockResolvedValue(report as never)
      const { unmount } = renderAt()
      await screen.findByRole('heading', { name: 'Sales' })
      await waitFor(() => expect(document.documentElement.getAttribute('data-theme')).toBe('light'))
      unmount()
      expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    } finally { localStorage.removeItem('theme'); document.documentElement.removeAttribute('data-theme') }
  })

  it('speaks Arabic', async () => {
    const { DirectionProvider } = await import('../contexts/DirectionContext')
    localStorage.setItem('datalytics.language', 'ar')
    try {
      vi.mocked(reportsApi.get).mockResolvedValue(report as never)
      render(<DirectionProvider><MemoryRouter initialEntries={['/reports/1/print']}>
        <Routes><Route path="/reports/:id/print" element={<ReportPrint />} /></Routes></MemoryRouter></DirectionProvider>)
      expect(await screen.findByRole('button', { name: 'طباعة / حفظ بصيغة PDF' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'العودة إلى التقرير' })).toBeInTheDocument()
      expect(screen.getByText('صفحتان')).toBeInTheDocument()
    } finally { localStorage.removeItem('datalytics.language') }
  })
})
