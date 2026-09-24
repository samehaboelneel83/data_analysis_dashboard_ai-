import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MappingMatch } from './ModelView'
import ModelView from './ModelView'
import { relationshipsApi } from '../../services/api'

vi.mock('../../services/api', () => ({ relationshipsApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn(), check: vi.fn() } }))

const REPORT = { id: 1, dataset_id: 10, additional_dataset_ids: [20] } as any
const DATASETS = {
  10: { id: 10, name: 'Orders', columns: [{ id: 1, name: 'customer_id', dtype: 'numeric', missing_pct: 0, stats: {} }] },
  20: { id: 20, name: 'Customers', columns: [{ id: 2, name: 'id', dtype: 'numeric', missing_pct: 0, stats: {} }] },
} as any

describe('ModelView diagram', () => {
  it('shows a box for each dataset attached to the report', async () => {
    vi.mocked(relationshipsApi.list).mockResolvedValue([])
    render(<ModelView report={REPORT} datasets={DATASETS} />)
    expect(await screen.findByText('Orders')).toBeInTheDocument()
    expect(screen.getByText('Customers')).toBeInTheDocument()
  })

  it('shows an existing relationship between the two datasets', async () => {
    vi.mocked(relationshipsApi.list).mockResolvedValue([
      { id: 1, org_id: 1, from_dataset_id: 10, from_column: 'customer_id', to_dataset_id: 20, to_column: 'id',
        created_at: '2026-01-01', source: 'declared', confidence: 1.0 },
    ])
    render(<ModelView report={REPORT} datasets={DATASETS} />)
    expect(await screen.findByText(/customer_id.*↔.*id/)).toBeInTheDocument()
  })
})

describe('MappingMatch (Phase 6.1)', () => {
  it('says what share of clicks will land, what is missing, and the near misses', () => {
    render(<MappingMatch fromCol="country" toCol="cust_country" check={{
      source_values: 4, matched_values: 2, pct_values: 50, target_values: 4, pct_target_covered: 50,
      unmatched: [{ value: 'Saudi Arabia', rows: 3 }, { value: 'Oman', rows: 1 }], unmatched_count: 2,
      near_matches: [{ source: 'Saudi Arabia', target: 'saudi arabia' }], type_mismatch: null,
    }} />)
    const box = screen.getByTestId('mapping-match')
    expect(box.textContent).toContain('50% of country’s values exist in cust_country')
    expect(box.textContent).toContain('Not found: Saudi Arabia, Oman')
    expect(box.textContent).toContain('differ only in case or spacing')
  })
})
