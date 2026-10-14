import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import MeaningCard from './MeaningCard'
import { setupApi, type SetupMeaning } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { meaning: vi.fn(), refreshMeaning: vi.fn(), editMeaning: vi.fn() } }
})

const map = (over: Partial<SetupMeaning> = {}): SetupMeaning => ({
  pending: false, failed: null, built: true, rejected: [], min_base: 30,
  kinds: ['amount', 'level', 'duration', 'score', 'share', 'count', 'code'],
  lines: [
    { kind: 'base', subject: 'complaints>shipments', text: 'Complaints are counted against Shipments: about 36 for every 1,000 shipments.' },
    { kind: 'outcome', subject: 'shipments.is_late', text: 'Shipments: is late — 18%' },
    { kind: 'numbers', subject: 'add', text: 'Add up: delivery fee egp (EGP).' }],
  numbers: [{ subject: 'shipments.customer_rating', table: 'shipments', column: 'customer_rating', kind: 'score',
              unit: '', direction: 'higher_better', source: 'ai' }],
  ...over,
})

beforeEach(() => vi.clearAllMocks())

describe('Guided setup — how to read this database', () => {
  it('says in plain sentences what is counted against what', async () => {
    vi.mocked(setupApi.meaning).mockResolvedValue(map())
    render(<MeaningCard sourceId={43} canEdit />)
    expect(await screen.findByText(/about 36 for every 1,000 shipments/)).toBeInTheDocument()
    expect(screen.getByText('Add up: delivery fee egp (EGP).')).toBeInTheDocument()
  })

  it('lets a person say a fact is not right, and it is then left out', async () => {
    vi.mocked(setupApi.meaning).mockResolvedValue(map())
    vi.mocked(setupApi.editMeaning).mockResolvedValue(map({ lines: [], rejected: [{ kind: 'base', subject: 'complaints>shipments' }] }))
    render(<MeaningCard sourceId={43} canEdit />)
    fireEvent.click(await screen.findByRole('button', { name: /^Not right: Complaints are counted/ }))
    await waitFor(() => expect(setupApi.editMeaning).toHaveBeenCalledWith(
      43, { kind: 'base', subject: 'complaints>shipments', status: 'rejected' }, 'en'))
  })

  it('lets a person change what a number is, behind the details', async () => {
    vi.mocked(setupApi.meaning).mockResolvedValue(map())
    vi.mocked(setupApi.editMeaning).mockResolvedValue(map())
    render(<MeaningCard sourceId={43} canEdit />)
    fireEvent.click(await screen.findByRole('button', { name: 'Show details' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'What kind of number is customer_rating' }), { target: { value: 'level' } })
    await waitFor(() => expect(setupApi.editMeaning).toHaveBeenCalledWith(
      43, { kind: 'number', subject: 'shipments.customer_rating', number_kind: 'level' }, 'en'))
  })

  it('says it is measuring while it works, and offers no edits to a reader who may not change it', async () => {
    vi.mocked(setupApi.meaning).mockResolvedValue(map({ pending: true, built: false, lines: [], numbers: [] }))
    const { unmount } = render(<MeaningCard sourceId={43} canEdit={false} />)
    expect(await screen.findByText(/Measuring what is counted against what/)).toBeInTheDocument()
    unmount()
    vi.mocked(setupApi.meaning).mockResolvedValue(map())
    render(<MeaningCard sourceId={43} canEdit={false} />)
    await screen.findByText(/about 36 for every/)
    expect(screen.queryByRole('button', { name: /Not right/ })).not.toBeInTheDocument()
  })
})
