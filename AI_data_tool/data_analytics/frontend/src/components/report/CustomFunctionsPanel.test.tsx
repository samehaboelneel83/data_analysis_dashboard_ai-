import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import CustomFunctionsPanel from './CustomFunctionsPanel'

vi.mock('../../services/api', () => ({
  customFunctionsApi: { list: vi.fn(), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
}))

import { customFunctionsApi } from '../../services/api'

const PROFIT_MARGIN = { name: 'PROFIT_MARGIN', params: ['revenue', 'cost'], expression: '(revenue - cost) / revenue' }

describe('CustomFunctionsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(customFunctionsApi.list).mockResolvedValue([])
  })

  it('lists existing functions and notifies the parent on load', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([PROFIT_MARGIN])
    const onChanged = vi.fn()
    render(<CustomFunctionsPanel datasetId={5} onChanged={onChanged} />)

    expect(await screen.findByText('PROFIT_MARGIN(revenue, cost)')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledWith([PROFIT_MARGIN])
  })

  it('shows an empty state when there are none', async () => {
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)
    expect(await screen.findByText(/no custom functions/i)).toBeInTheDocument()
  })

  it('creates a new function and shows the validation error inline on failure', async () => {
    vi.mocked(customFunctionsApi.save).mockRejectedValue({ response: { data: { detail: "'SUM' is already a built-in function — pick another name" } } })
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /new function/i }))
    fireEvent.change(screen.getByLabelText(/function name/i), { target: { value: 'SUM' } })
    fireEvent.change(screen.getByLabelText(/^expression$/i), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText(/already a built-in function/)).toBeInTheDocument()
  })

  it('deletes a function', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([PROFIT_MARGIN])
    vi.mocked(customFunctionsApi.delete).mockResolvedValue([])
    const onChanged = vi.fn()
    render(<CustomFunctionsPanel datasetId={5} onChanged={onChanged} />)

    fireEvent.click(await screen.findByTitle('Delete'))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(customFunctionsApi.delete).toHaveBeenCalledWith(5, 'PROFIT_MARGIN'))
    expect(onChanged).toHaveBeenLastCalledWith([])
  })

  it('edits an existing function: pre-fills the form and saves the updated definition', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([PROFIT_MARGIN])
    vi.mocked(customFunctionsApi.save).mockResolvedValue([
      { name: 'PROFIT_MARGIN', params: ['revenue', 'cost'], expression: '(revenue - cost) / cost' },
    ])
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByTitle('Edit'))

    expect(screen.getByLabelText(/function name/i)).toHaveValue('PROFIT_MARGIN')
    expect(screen.getByLabelText(/parameters/i)).toHaveValue('revenue, cost')
    expect(screen.getByLabelText(/^expression$/i)).toHaveValue('(revenue - cost) / revenue')

    fireEvent.change(screen.getByLabelText(/^expression$/i), { target: { value: '(revenue - cost) / cost' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(customFunctionsApi.save).toHaveBeenCalledWith(5,
      { name: 'PROFIT_MARGIN', params: ['revenue', 'cost'], expression: '(revenue - cost) / cost' }))
  })

  it('previews a definition against sample values before saving', async () => {
    vi.mocked(customFunctionsApi.preview).mockResolvedValue({ ok: true, result: 0.6 })
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /new function/i }))
    fireEvent.change(screen.getByLabelText(/function name/i), { target: { value: 'PROFIT_MARGIN' } })
    fireEvent.change(screen.getByLabelText(/parameters/i), { target: { value: 'revenue, cost' } })
    fireEvent.change(screen.getByLabelText(/^expression$/i), { target: { value: '(revenue - cost) / revenue' } })
    fireEvent.change(screen.getByLabelText(/sample value for revenue/i), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText(/sample value for cost/i), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: /test/i }))

    expect(await screen.findByText('0.6')).toBeInTheDocument()
    // Sample values are coerced to numbers where parseable before the request
    // goes out -- the real backend evaluates them arithmetically
    // ((revenue - cost) / revenue), and a raw string '100' would fail that
    // arithmetic where a real dataset column never would (pandas coerces a
    // numeric CSV column to a numeric dtype on load; a hand-typed sample
    // value has no such pipeline).
    expect(customFunctionsApi.preview).toHaveBeenCalledWith(5, ['revenue', 'cost'], '(revenue - cost) / revenue', { revenue: 100, cost: 40 })
  })
})
