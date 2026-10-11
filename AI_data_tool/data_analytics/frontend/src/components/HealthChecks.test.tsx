import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const health = vi.fn()
vi.mock('../services/api', () => ({ discoveryApi: { health: (id: number) => health(id) } }))
vi.mock('../i18n', () => ({ en: {}, useT: () => (k: string, v?: Record<string, unknown>) => v?.n != null ? `${k}:${v.n}` : k }))

import HealthChecks from './HealthChecks'

const check = (id: string, status: string, extra: Record<string, unknown> = {}) =>
  ({ id, group: 'values', status, title: `title ${id}`, sentence: `sentence ${id}`, columns: [], figures: extra })

describe('a dataset\'s health', () => {
  it('shows the problems first and keeps what passed behind Show details', async () => {
    health.mockResolvedValue({ dataset_id: 1, restricted: false,
      summary: { pass: 3, warn: 1, fail: 1, status: 'fail', not_checked: 1, columns: 6, rows: 100, sampled: false },
      checks: [check('duplicates', 'fail'), check('missing', 'warn'),
               check('volume', 'pass', { series: [['2025-01', 10], ['2025-02', 12]] }),
               check('mistyped', 'pass'), check('constant', 'pass'), check('schema', 'pass', { checked: false })] })
    render(<HealthChecks datasetId={1} />)
    expect((await screen.findByTestId('health-summary')).textContent).toMatch(/3 hchk.pass · 1 hchk.warn · 1 hchk.fail/)
    expect(screen.getAllByTestId('health-check').map(e => e.getAttribute('data-status'))).toEqual(['fail', 'warn'])
    expect(screen.queryByText('Sentence volume')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'hchk.show:4' }))
    expect(screen.getByText('Sentence volume')).toBeTruthy()
    expect(screen.getByTestId('health-volume').children).toHaveLength(2)
    expect(screen.getAllByTestId('health-check').at(-1)?.getAttribute('data-status')).toBe('skipped')
  })

  it('says so in one line when nothing needs a look', async () => {
    health.mockResolvedValue({ dataset_id: 2, restricted: false,
      summary: { pass: 2, warn: 0, fail: 0, status: 'pass', not_checked: 0, columns: 2, rows: 5, sampled: false },
      checks: [check('missing', 'pass'), check('duplicates', 'pass')] })
    render(<HealthChecks datasetId={2} />)
    expect(await screen.findByText('hchk.allGood')).toBeTruthy()
    expect(screen.queryAllByTestId('health-check')).toHaveLength(0)
  })

  it('draws nothing when the server cannot say', async () => {
    health.mockRejectedValue(new Error('no'))
    const { container } = render(<HealthChecks datasetId={3} />)
    await Promise.resolve()
    expect(container.querySelector('[data-testid=dataset-health]')).toBeNull()
  })
})
