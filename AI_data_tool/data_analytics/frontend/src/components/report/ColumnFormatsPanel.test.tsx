import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ColumnFormatsPanel from './ColumnFormatsPanel'
import { columnFormatsApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', () => ({
  columnFormatsApi: { set: vi.fn().mockImplementation(async (_id: number, name: string, fmt: unknown) => (fmt ? { [name]: fmt } : {})) },
}))

const columns: DatasetColumn[] = [{ id: 1, name: 'score', dtype: 'number', missing_pct: 0, stats: {} }]

describe('ColumnFormatsPanel colorscale format', () => {
  it('shows Min/Max and three color pickers once Color Scale is chosen, and saves scaleMinColor', async () => {
    render(<ColumnFormatsPanel datasetId={1} columns={columns} columnFormats={{}} onChanged={vi.fn()} />)

    fireEvent.change(screen.getByDisplayValue('None'), { target: { value: 'colorscale' } })

    expect(await screen.findByText('Min')).toBeInTheDocument()
    expect(screen.getByText('Max')).toBeInTheDocument()
    expect(screen.getByText('Low')).toBeInTheDocument()
    expect(screen.getByText('Mid')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
  })
})

describe('ColumnFormatsPanel icon format', () => {
  it('shows Low/High threshold inputs once Icon Set is chosen', async () => {
    render(<ColumnFormatsPanel datasetId={1} columns={columns} columnFormats={{}} onChanged={vi.fn()} />)

    fireEvent.change(screen.getByDisplayValue('None'), { target: { value: 'icon' } })

    expect(await screen.findByText('Low (red)')).toBeInTheDocument()
    expect(screen.getByText('High (green)')).toBeInTheDocument()
  })

  it('writes thresholds when the Low input changes', async () => {
    render(<ColumnFormatsPanel datasetId={1} columns={columns} columnFormats={{}} onChanged={vi.fn()} />)

    fireEvent.change(screen.getByDisplayValue('None'), { target: { value: 'icon' } })
    fireEvent.change(await screen.findByPlaceholderText('33'), { target: { value: '20' } })

    await waitFor(() => {
      expect(vi.mocked(columnFormatsApi.set)).toHaveBeenCalledWith(1, 'score', expect.objectContaining({ thresholds: [20, 66] }))
    })
  })
})
