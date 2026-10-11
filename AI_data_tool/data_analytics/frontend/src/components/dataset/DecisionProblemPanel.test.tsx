import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const problems = vi.fn()
const specification = vi.fn()
vi.mock('../../services/api', () => ({ decisionApi: { problems: (id: number) => problems(id), specification: (id: number, b: unknown) => specification(id, b) } }))
vi.mock('../../i18n', () => ({ en: {}, useT: () => (k: string, v?: Record<string, unknown>) =>
  v && Object.keys(v).length ? `${k}:${Object.values(v).filter(x => x !== '').join(',')}` : k }))

import DecisionProblemPanel from './DecisionProblemPanel'

const SPEC = {
  schema: 'datalytics.decision-problem/1', problem: 'allocation', solved: false, note: '',
  objective: { direction: 'maximize', column: 'gain', aggregate: 'sum_over_chosen' },
  decisions: { unit: 'row', key: 'item', type: 'choose', domain: [0, 1], count: 40 },
  constraints: [{ kind: 'total_at_most', column: 'cost', value: 100 }],
  data: { rows: 40, columns: ['item', 'gain', 'cost'] },
  checks: [{ code: 'fit_alone', options: 38, of: 40 }], dataset: { id: 7, name: 'Things' },
}

beforeEach(() => { problems.mockReset(); specification.mockReset() })

describe('a decision to set up', () => {
  it('says in plain words when the table has no such shape, and what the shapes are', async () => {
    problems.mockResolvedValue({ dataset_id: 7, problems: [], restricted: false })
    render(<DecisionProblemPanel datasetId={7} />)
    expect((await screen.findByTestId('decision-none')).textContent).toContain('dcp.none')
    expect(screen.getByText('dcp.shape.allocation')).toBeTruthy()
    expect(screen.getByText('dcp.shape.assignment')).toBeTruthy()
  })

  it('sends exactly what the person chose and says what was written before showing the document', async () => {
    problems.mockResolvedValue({ dataset_id: 7, restricted: false,
      problems: [{ problem: 'allocation', key: 'item', amounts: ['gain', 'cost'], options: 40 }] })
    specification.mockResolvedValue(SPEC)
    render(<DecisionProblemPanel datasetId={7} />)
    await screen.findByTestId('decision-allocation')
    fireEvent.change(screen.getByLabelText('dcp.limit'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'dcp.write' }))
    await waitFor(() => expect(specification).toHaveBeenCalledWith(7,
      { problem: 'allocation', key: 'item', objective: 'gain', direction: 'largest', limited: 'cost', limit: 100 }))
    const said = await screen.findByTestId('decision-spec')
    expect(said.textContent).toContain('dcp.say.max:gain')
    expect(said.textContent).toContain('dcp.con.total_at_most:cost,100')
    expect(said.textContent).toContain('dcp.notSolved')
    expect(screen.getByTestId('decision-checks').textContent).toContain('dcp.chk.fit_alone')
    // Plain first: the document itself is behind "Show details".
    expect(screen.queryByTestId('decision-json')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'dcp.show' }))
    expect(screen.getByTestId('decision-json').textContent).toContain('datalytics.decision-problem/1')
  })

  it('shows the reason when what was chosen cannot be a decision', async () => {
    problems.mockResolvedValue({ dataset_id: 7, restricted: false,
      problems: [{ problem: 'assignment', from: 'worker', to: 'task', numbers: ['hours'], pairs: 30, fill: 1 }] })
    specification.mockRejectedValue({ response: { data: { detail: '6 of worker cannot each be matched' } } })
    render(<DecisionProblemPanel datasetId={7} />)
    await screen.findByTestId('decision-assignment')
    fireEvent.change(screen.getByLabelText('dcp.eachFrom:worker'), { target: { value: 'exactly_one' } })
    fireEvent.click(screen.getByRole('button', { name: 'dcp.write' }))
    expect((await screen.findByRole('alert')).textContent).toContain('cannot each be matched')
    expect(specification).toHaveBeenCalledWith(7, { problem: 'assignment', from_col: 'worker', to_col: 'task', objective: 'hours',
      direction: 'smallest', each_from: 'exactly_one', each_to_at_most: 1 })
    expect(screen.queryByTestId('decision-spec')).toBeNull()
  })
})
