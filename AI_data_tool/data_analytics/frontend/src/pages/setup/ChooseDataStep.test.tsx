import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ChooseDataStep from './ChooseDataStep'
import { jobsApi, setupApi, type SetupDatasetsStep, type SetupProposal } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return {
    ...real,
    setupApi: { datasets: vi.fn(), suggestDatasets: vi.fn(), refineDataset: vi.fn(), createDatasets: vi.fn(), update: vi.fn() },
    jobsApi: { ...real.jobsApi, get: vi.fn() },
  }
})

const proposal = (over: Partial<SetupProposal> = {}): SetupProposal => ({
  id: 'p1', name: 'Car prices', purpose: 'Prices by brand, age and city.', sql: 'SELECT price FROM cars',
  tables: ['cars'], includes: ['Price', 'Brand'], leaves_out: ['Arabic copies', 'Seller phones'],
  why: 'You price used cars.', source: 'ai',
  test: { columns: ['price', 'make'], rows: [{ price: 100, make: null }], row_count: 14269, error: null },
  history: [], ...over,
})

const step = (over: Partial<SetupDatasetsStep> = {}): SetupDatasetsStep => ({
  proposals: { pending: false, failed: null, items: [proposal()], language: 'en', asked: true },
  brief: { work: 'I sell used cars' }, existing: [], chosen: [], can_create: true, allow_ai: true, ...over,
})

const renderStep = (onDone = vi.fn().mockResolvedValue(undefined)) => {
  render(<MemoryRouter><ChooseDataStep sourceId={38} onDone={onDone} /></MemoryRouter>)
  return onDone
}

beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })

describe('Guided setup — Choose data', () => {
  it('asks About you first, then suggests with the answers', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step({
      proposals: { pending: false, failed: null, items: [], language: null, asked: false }, brief: {} }))
    vi.mocked(setupApi.suggestDatasets).mockResolvedValue({ proposals: step().proposals })
    renderStep()
    fireEvent.change(await screen.findByLabelText('What is your work?'), { target: { value: 'Lawyer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest datasets' }))
    await waitFor(() => expect(setupApi.update).toHaveBeenCalledWith(38, { brief: { work: 'Lawyer' } }))
    expect(setupApi.suggestDatasets).toHaveBeenCalledWith(38, 'en')
  })

  it('can skip About you', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step({
      proposals: { pending: false, failed: null, items: [], language: null, asked: false }, brief: {} }))
    vi.mocked(setupApi.suggestDatasets).mockResolvedValue({ proposals: step().proposals })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Skip and suggest' }))
    await waitFor(() => expect(setupApi.suggestDatasets).toHaveBeenCalled())
  })

  it('shows each suggestion with what it includes, leaves out and why', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step())
    renderStep()
    expect(await screen.findByRole('heading', { name: 'Car prices' })).toBeInTheDocument()
    expect(screen.getByText('Seller phones')).toBeInTheDocument()
    expect(screen.getByText('You price used cars.')).toBeInTheDocument()
    expect(screen.getByText('14,269 rows')).toBeInTheDocument()
    expect(screen.getByText('I sell used cars')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show sample rows' }))
    expect(screen.getByText('Empty')).toBeInTheDocument()
  })

  it('sends a change asked in plain words', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step())
    vi.mocked(setupApi.refineDataset).mockResolvedValue({ proposals: step().proposals })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Change it' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Ask for a change/ }), { target: { value: 'only 2015 and newer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(setupApi.refineDataset).toHaveBeenCalledWith(38, 'p1', 'only 2015 and newer', 'en'))
  })

  it('creates the chosen dataset, waits for the import, then moves on', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step())
    vi.mocked(setupApi.createDatasets).mockResolvedValue({ items: [
      { proposal_id: 'p1', name: 'Car prices', job_id: 9, dataset_id: null, error: null }] })
    vi.mocked(jobsApi.get).mockResolvedValue({ id: 9, state: 'succeeded', result: { dataset_id: 501 } } as never)
    const onDone = renderStep()
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Use "Car prices"' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create 1 dataset and continue' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith([501]))
    expect(setupApi.createDatasets).toHaveBeenCalledWith(38, [{ id: 'p1', name: 'Car prices' }], 'import')
  })

  it('can use datasets that already exist instead', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step({ existing: [{ id: 7, name: 'cars_hatla2ee', rows: 14269, mode: 'import' }] }))
    const onDone = renderStep()
    fireEvent.click(await screen.findByRole('checkbox', { name: /cars_hatla2ee/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next: Check & discover' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith([7]))
    expect(setupApi.createDatasets).not.toHaveBeenCalled()
  })

  it('says plainly when someone may not create datasets', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step({ can_create: false }))
    renderStep()
    expect(await screen.findByText(/Only an admin can create datasets/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Use "Car prices"' })).not.toBeInTheDocument()
  })

  it('explains suggestions made without the AI', async () => {
    vi.mocked(setupApi.datasets).mockResolvedValue(step({ proposals: {
      pending: false, failed: 'off', items: [proposal({ source: 'auto' })], language: 'en', asked: true } }))
    renderStep()
    expect(await screen.findByText(/AI is off for this connection/)).toBeInTheDocument()
  })
})
