import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import CommandPalette, { matchScore } from './CommandPalette'
import { reportsApi, datasetsApi, dataSourcesApi } from '../services/api'

vi.mock('../services/api', () => ({
  reportsApi: { list: vi.fn() },
  datasetsApi: { list: vi.fn() },
  dataSourcesApi: { list: vi.fn() },
}))

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{loc.pathname}</div>
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(reportsApi.list).mockResolvedValue([{ id: 7, name: 'Quarterly Sales' }] as never)
  vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 3, name: 'Orders', mode: 'import' }] as never)
  vi.mocked(dataSourcesApi.list).mockResolvedValue([{ id: 9, name: 'Prod Postgres' }] as never)
})

function mount() {
  return render(
    <MemoryRouter>
      <Routes><Route path="*" element={<><CommandPalette /><LocationProbe /></>} /></Routes>
    </MemoryRouter>
  )
}

describe('CommandPalette', () => {
  it('opens on Ctrl+K, searches reports and datasets, Enter navigates', async () => {
    mount()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = await screen.findByLabelText('Search everything')
    await waitFor(() => expect(reportsApi.list).toHaveBeenCalled())
    fireEvent.change(input, { target: { value: 'quart' } })
    expect(await screen.findByText('Quarterly Sales')).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('loc')).toHaveTextContent('/reports/7')
    expect(screen.queryByLabelText('Search everything')).not.toBeInTheDocument()
  })

  it('ranks prefix over substring and supports fuzzy subsequence', async () => {
    mount()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = await screen.findByLabelText('Search everything')
    await waitFor(() => expect(datasetsApi.list).toHaveBeenCalled())
    fireEvent.change(input, { target: { value: 'ord' } })
    expect(await screen.findByText('Orders')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'qtl' } })      // fuzzy: QuarTerLy
    expect(await screen.findByText('Quarterly Sales')).toBeInTheDocument()
  })

  it('indexes connections and navigates to the connection review page', async () => {
    mount()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = await screen.findByLabelText('Search everything')
    await waitFor(() => expect(dataSourcesApi.list).toHaveBeenCalled())
    fireEvent.change(input, { target: { value: 'postgres' } })
    expect(await screen.findByText('Prod Postgres')).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('loc')).toHaveTextContent('/connections/9/review')
  })

  it('closes on Escape', async () => {
    mount()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    await screen.findByLabelText('Search everything')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByLabelText('Search everything')).not.toBeInTheDocument()
  })

  it('groups results under headings and offers commands', async () => {
    mount()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = await screen.findByLabelText('Search everything')
    await waitFor(() => expect(reportsApi.list).toHaveBeenCalled())
    fireEvent.change(input, { target: { value: 'upload' } })
    expect(await screen.findByText('Upload a file')).toBeInTheDocument()
    expect(screen.getByText('Commands')).toBeInTheDocument()
    expect(screen.getByText('Pages')).toBeInTheDocument()
  })
})

describe('matchScore', () => {
  it('prefers a prefix, then a word, then a substring', () => {
    expect(matchScore('quarterly sales', 'quar')).toBe(0)
    expect(matchScore('quarterly sales', 'sal')).toBe(1)
    expect(matchScore('quarterly sales', 'rterl')).toBe(2)
  })
  it('only takes a compact subsequence that starts a word', () => {
    expect(matchScore('quarterly sales', 'qtl')).toBe(3)
    // letters scattered across a long name are not a match any more
    expect(matchScore('students attendance log export', 'sales')).toBe(-1)
    expect(matchScore('orders', 'os')).toBe(-1)
  })
})
