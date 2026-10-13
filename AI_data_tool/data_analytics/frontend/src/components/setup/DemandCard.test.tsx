import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import DemandCard from './DemandCard'
import type { SetupDemand, SetupScope } from '../../services/api'

// Persona test 2026-10-12 (docs/persona-test, plan 0.2): "the year 2023" is a
// range; it read "Only trade date between 2023-01-01", once per dataset.
const range = (dataset_id: number): SetupScope => ({
  dataset_id, said: 'the year 2023', column: 'trade_date', op: 'between',
  values: ['2023-01-01', '2023-12-31'], matched_rows: 10, of_rows: 10, status: 'in_data',
})

const demand = (scope: SetupScope[]): SetupDemand => ({
  pending: false, failed: null, written: true, sentence: 'Prices in one year', who: '', subject: '',
  questions: [], exclude: [], scope, source: 'ai', edits: [], language: 'en',
})

describe('DemandCard', () => {
  it('reads a range with both ends, once for every dataset that holds it', () => {
    render(<DemandCard sourceId={1} demand={demand([range(1), range(2), range(3)])} onChanged={() => {}} />)
    const lines = screen.getAllByText(/trade date: 2023-01-01 – 2023-12-31/)
    expect(lines).toHaveLength(1)
  })
})
