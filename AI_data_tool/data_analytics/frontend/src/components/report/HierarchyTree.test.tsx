import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import HierarchyTree from './HierarchyTree'
import { hierarchyApi } from '../../services/api'
import type { HierarchyNode } from '../../types/report'

vi.mock('../../services/api', () => ({
  hierarchyApi: { update: vi.fn(), delete: vi.fn() },
}))

function node(overrides: Partial<HierarchyNode> = {}): HierarchyNode {
  return {
    id: 1, dataset_id: 10, parent_id: null, name: 'Region', node_type: 'dimension',
    position: 0, created_at: '2026-01-01', ...overrides,
  }
}

function folder(id: number, name: 'Dimensions' | 'Measures'): HierarchyNode {
  return { id, dataset_id: 10, parent_id: null, name, node_type: 'folder', position: 0, created_at: '2026-01-01' }
}

describe('HierarchyTree row-hover action reveal', () => {
  it('reveals the edit/delete actions when hovering the row, not just the action icons themselves', () => {
    render(<HierarchyTree nodes={[node()]} datasetId={10} onRefresh={vi.fn()} />)

    const row = screen.getByText('Region').closest('div') as HTMLElement
    const actions = row.querySelector('.node-actions') as HTMLElement

    expect(actions.style.opacity).toBe('0')
    fireEvent.mouseEnter(row)
    expect(actions.style.opacity).toBe('1')
    fireEvent.mouseLeave(row)
    expect(actions.style.opacity).toBe('0')
  })
})

describe('HierarchyTree type reclassification', () => {
  it('switches a dimension node to a measure and re-parents it under the Measures folder', async () => {
    const dims = folder(100, 'Dimensions')
    const meas = folder(200, 'Measures')
    const region = node({ id: 1, parent_id: 100, name: 'Region', node_type: 'dimension' })
    const onRefresh = vi.fn()
    render(<HierarchyTree nodes={[dims, meas, region]} datasetId={10} onRefresh={onRefresh} />)

    fireEvent.click(screen.getByRole('button', { name: /Switch to Measure/i }))

    await waitFor(() => expect(hierarchyApi.update).toHaveBeenCalledWith(10, 1, { node_type: 'measure', parent_id: 200 }))
    await waitFor(() => expect(onRefresh).toHaveBeenCalled())
  })

  it('switches a measure node back to a dimension and re-parents it under the Dimensions folder', async () => {
    const dims = folder(100, 'Dimensions')
    const meas = folder(200, 'Measures')
    const revenue = node({ id: 2, parent_id: 200, name: 'Revenue', node_type: 'measure' })
    render(<HierarchyTree nodes={[dims, meas, revenue]} datasetId={10} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /Switch to Category/i }))

    await waitFor(() => expect(hierarchyApi.update).toHaveBeenCalledWith(10, 2, { node_type: 'dimension', parent_id: 100 }))
  })

  it('does not show the type toggle for folder, date, or text nodes', () => {
    const dateNode = node({ id: 3, name: 'Order Date', node_type: 'date' })
    render(<HierarchyTree nodes={[dateNode]} datasetId={10} onRefresh={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Switch to Measure/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Switch to Category/i })).not.toBeInTheDocument()
  })
})


describe('HierarchyTree date-hierarchy editing', () => {
  beforeEach(() => { vi.clearAllMocks() })
  const dateChain = [
    node({ id: 1, name: 'Dates', node_type: 'folder' }),
    node({ id: 2, name: 'Year', node_type: 'date', parent_id: 1, column_name: 'd', format: 'year' }),
    node({ id: 3, name: 'Quarter', node_type: 'date', parent_id: 2, column_name: 'd', format: 'quarter' }),
    node({ id: 4, name: 'Month', node_type: 'date', parent_id: 3, column_name: 'd', format: 'month' }),
  ]

  it('date levels expose a granularity select that PATCHes format', async () => {
    render(<HierarchyTree nodes={dateChain} datasetId={10} onRefresh={() => {}} />)
    fireEvent.change(screen.getByLabelText('Granularity of Month'), { target: { value: 'week' } })
    await waitFor(() => expect(hierarchyApi.update).toHaveBeenCalledWith(10, 4, { format: 'week' }))
  })

  it('move-up swaps a level with its parent and re-links the old child', async () => {
    render(<HierarchyTree nodes={dateChain} datasetId={10} onRefresh={() => {}} />)
    fireEvent.click(screen.getByLabelText('Move Quarter up'))
    await waitFor(() => expect(hierarchyApi.update).toHaveBeenCalledTimes(3))
    const calls = vi.mocked(hierarchyApi.update).mock.calls
    expect(calls[0]).toEqual([10, 3, { parent_id: 1 }])   // quarter -> under the folder
    expect(calls[1]).toEqual([10, 2, { parent_id: 3 }])   // year becomes quarter's child
    expect(calls[2]).toEqual([10, 4, { parent_id: 2 }])   // month re-links under year
  })

  it('a level directly under a folder offers no move-up', () => {
    render(<HierarchyTree nodes={dateChain} datasetId={10} onRefresh={() => {}} />)
    expect(screen.queryByLabelText('Move Year up')).not.toBeInTheDocument()
  })
})
