import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import OutlierDetailsDialog from './OutlierDetailsDialog'
import { outlierApi } from '../../services/api'

vi.mock('../../services/api', () => ({ outlierApi: { details: vi.fn() } }))

const details = {
  column: 'amount',
  stats: { min: 10, q1: 10, median: 12, q3: 12, max: 1000, fence_low: 7, fence_high: 15 },
  outliers: { count: 1, total_rows: 21, columns: ['who', 'amount'], rows: [['r20', 1000]] },
  impact: { share_of_sum: 0.8197, mean_with: 58.1, mean_without: 11 },
}

beforeEach(() => { vi.clearAllMocks() })

describe('OutlierDetailsDialog', () => {
  it('shows fences, impact and the outlier rows', async () => {
    vi.mocked(outlierApi.details).mockResolvedValue(details)
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText(/fall beyond 1.5×IQR/)).toBeInTheDocument())
    expect(screen.getByText(/82.0%/)).toBeInTheDocument()
    expect(screen.getByText('r20')).toBeInTheDocument()
    expect(screen.getByTestId('boxplot')).toBeInTheDocument()
  })

  it('surfaces the server error for a denied or missing column', async () => {
    vi.mocked(outlierApi.details).mockRejectedValue({ response: { data: { detail: "Column 'amount' not found" } } })
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('not found'))
  })

  it('closes on backdrop click but not on content click', async () => {
    vi.mocked(outlierApi.details).mockResolvedValue(details)
    const onClose = vi.fn()
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={onClose} />)
    await screen.findByText(/fall beyond/)
    fireEvent.click(screen.getByText('r20'))
    expect(onClose).not.toHaveBeenCalled()

    // role="dialog" now sits on the PANEL, where it belongs -- the backdrop is
    // not the dialog, it is the scrim behind it. So the backdrop is reached as
    // the panel's parent rather than by role.
    const backdrop = screen.getByRole('dialog').parentElement!
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalled()
  })

  it('defaults to the iqr detector and re-fetches when the detector changes', async () => {
    vi.mocked(outlierApi.details).mockResolvedValue(details)
    render(<OutlierDetailsDialog datasetId={5} column="amount" onClose={() => {}} />)
    await screen.findByText(/fall beyond/)
    expect(outlierApi.details).toHaveBeenCalledWith(5, 'amount', 'iqr')

    fireEvent.change(screen.getByLabelText('Detector'), { target: { value: 'iforest' } })
    await waitFor(() => expect(outlierApi.details).toHaveBeenCalledWith(5, 'amount', 'iforest'))
  })
})
