import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChangeDataDialog from './ChangeDataDialog'
import { jobsApi, setupApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { changeOptions: vi.fn(), changePreview: vi.fn(), changeApply: vi.fn() },
           jobsApi: { ...real.jobsApi, get: vi.fn() } }
})

const opts = {
  can_change: true, reason: null, columns: ['price', 'make'], allow_ai: true, source: { id: 38, name: 'Cars DB' },
  addable: [{ name: 'item_url', table: 'cars', dtype: 'text', semantic_type: 'url', description: 'The car’s web link' }],
}

beforeEach(() => vi.clearAllMocks())

describe('Change the data', () => {
  it('adds a ticked column after showing what changes, and keeps the dataset', async () => {
    vi.mocked(setupApi.changeOptions).mockResolvedValue(opts)
    vi.mocked(setupApi.changePreview).mockResolvedValue({ error: null, sql: 'SELECT price, make, item_url FROM cars',
      adds: ['item_url'], removes: [], blocked: [], test: { columns: ['price', 'make', 'item_url'], rows: [{ price: 1, make: 'Kia', item_url: 'https://x/1' }], row_count: 9319 } })
    vi.mocked(setupApi.changeApply).mockResolvedValue({ job_id: 5 })
    vi.mocked(jobsApi.get).mockResolvedValue({ id: 5, state: 'succeeded', result: {} } as never)
    const onChanged = vi.fn(), onClose = vi.fn()
    render(<ChangeDataDialog datasetId={226} datasetName="Cars 2015+" onClose={onClose} onChanged={onChanged} />)
    fireEvent.click(await screen.findByRole('checkbox', { name: /item_url/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Preview with 1 column added' }))
    expect(await screen.findByText('Adds: item_url')).toBeInTheDocument()
    expect(screen.getByText('Removes: —')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Apply the change' }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(setupApi.changeApply).toHaveBeenCalledWith(226, 'SELECT price, make, item_url FROM cars')
  })

  it('asks in plain words', async () => {
    vi.mocked(setupApi.changeOptions).mockResolvedValue(opts)
    vi.mocked(setupApi.changePreview).mockResolvedValue({ error: 'failed' })
    render(<ChangeDataDialog datasetId={226} datasetName="Cars" onClose={vi.fn()} onChanged={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText('Or ask for a change'), { target: { value: 'I need the link of each car' } })
    fireEvent.click(screen.getByRole('button', { name: /Ask AI/ }))
    await waitFor(() => expect(setupApi.changePreview).toHaveBeenCalledWith(226, { message: 'I need the link of each car' }, 'en'))
    expect(await screen.findByText(/could not be made/)).toBeInTheDocument()
  })

  it('will not apply a change that removes what dashboards use', async () => {
    vi.mocked(setupApi.changeOptions).mockResolvedValue(opts)
    vi.mocked(setupApi.changePreview).mockResolvedValue({ error: null, sql: 'SELECT price FROM cars', adds: [], removes: ['make'],
      blocked: [{ column: 'make', used_by: [] }], test: { columns: ['price'], rows: [], row_count: 10 } })
    render(<ChangeDataDialog datasetId={226} datasetName="Cars" onClose={vi.fn()} onChanged={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText('Or ask for a change'), { target: { value: 'drop make' } })
    fireEvent.click(screen.getByRole('button', { name: /Ask AI/ }))
    expect(await screen.findByText(/remove columns your dashboards use \(make\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply the change' })).toBeDisabled()
  })

  it('says why when the data cannot be changed here', async () => {
    vi.mocked(setupApi.changeOptions).mockResolvedValue({ ...opts, can_change: false, reason: 'admin_only' })
    render(<ChangeDataDialog datasetId={226} datasetName="Cars" onClose={vi.fn()} onChanged={vi.fn()} />)
    expect(await screen.findByText(/Only an admin can change/)).toBeInTheDocument()
  })
})
