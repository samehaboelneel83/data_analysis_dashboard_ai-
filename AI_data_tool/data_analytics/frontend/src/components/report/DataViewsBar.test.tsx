import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DataViewsBar from './DataViewsBar'
import { dataViewsApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  dataViewsApi: { list: vi.fn(), save: vi.fn(), apply: vi.fn(), delete: vi.fn(), setDefault: vi.fn() },
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataViewsApi.list).mockResolvedValue([{ id: 3, name: 'Sales semantics', pieces: ['column_formats'] }])
})

describe('DataViewsBar', () => {
  it('saves the current dataset as a named view', async () => {
    vi.mocked(dataViewsApi.save).mockResolvedValue({ id: 9, name: 'Q2' })
    render(<DataViewsBar datasetId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Save current as view/ }))
    fireEvent.change(screen.getByLabelText('Data view name'), { target: { value: 'Q2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(dataViewsApi.save).toHaveBeenCalledWith(7, 'Q2'))
    expect(screen.getByTestId('dataview-status')).toHaveTextContent('Saved data view "Q2"')
  })

  it('applies a view and reports applied and skipped pieces verbatim', async () => {
    vi.mocked(dataViewsApi.apply).mockResolvedValue({
      applied: { column_formats: 2, calculated_columns: 1 },
      skipped: ["measure 'total_profit' (needs cost)"],
    })
    const onApplied = vi.fn()
    render(<DataViewsBar datasetId={7} onApplied={onApplied} />)
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply to this dataset' }))
    await waitFor(() => expect(dataViewsApi.apply).toHaveBeenCalledWith(7, 3))
    const status = screen.getByTestId('dataview-status')
    expect(status).toHaveTextContent('column formats: 2')
    expect(status).toHaveTextContent("skipped 1: measure 'total_profit' (needs cost)")
    expect(onApplied).toHaveBeenCalled()
  })

  it('disables apply until a view is chosen', async () => {
    render(<DataViewsBar datasetId={7} />)
    expect(await screen.findByRole('button', { name: 'Apply to this dataset' })).toBeDisabled()
  })
})

describe('the view applied to new datasets', () => {
  /**
   * SAS's admin default. Data views were already org-wide — the piece missing
   * was "and use this one on everything uploaded from now on", which saves an
   * organisation from re-declaring that `amount` is a currency measure on every
   * single import.
   *
   * Admin-only, because it changes what every future upload looks like for
   * everybody; the server refuses either way, and hiding the control keeps a
   * non-admin from meeting a 403 they could not have predicted.
   */
  const asAdmin = { isAdmin: true }

  it('offers the toggle to an admin', async () => {
    render(<DataViewsBar datasetId={7} {...asAdmin} />)
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    expect(screen.getByLabelText(/default for new datasets/i)).toBeInTheDocument()
  })

  it('does not offer it to anyone else', async () => {
    render(<DataViewsBar datasetId={7} />)
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    expect(screen.queryByLabelText(/default for new datasets/i)).not.toBeInTheDocument()
  })

  it('turns it on for the chosen view', async () => {
    vi.mocked(dataViewsApi.setDefault).mockResolvedValue({ id: 3, name: 'Sales semantics', is_default: true })
    render(<DataViewsBar datasetId={7} {...asAdmin} />)
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    fireEvent.click(screen.getByLabelText(/default for new datasets/i))
    await waitFor(() => expect(dataViewsApi.setDefault).toHaveBeenCalledWith(3, true))
  })

  it('shows which view is already the default', async () => {
    vi.mocked(dataViewsApi.list).mockResolvedValue([
      { id: 3, name: 'Sales semantics', pieces: [], is_default: true }])
    render(<DataViewsBar datasetId={7} {...asAdmin} />)
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    await waitFor(() =>
      expect(screen.getByLabelText(/default for new datasets/i)).toBeChecked())
  })

  it('says what turning it on means', async () => {
    // Nobody should have to discover from a surprising upload that every new
    // dataset now arrives with someone else's semantic layer on it.
    render(<DataViewsBar datasetId={7} {...asAdmin} />)
    fireEvent.change(await screen.findByLabelText('Saved data views'), { target: { value: '3' } })
    expect(screen.getByText(/applied to every dataset uploaded into this organisation/i))
      .toBeInTheDocument()
  })
})
