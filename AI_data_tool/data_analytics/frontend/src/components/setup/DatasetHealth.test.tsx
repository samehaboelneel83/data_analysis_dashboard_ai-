import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DatasetHealth from './DatasetHealth'
import { setupApi, type SetupFindings } from '../../services/api'
import { isMissingLabel } from '../../lib/missingLabel'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { findings: vi.fn(), datasetHealth: vi.fn(), datasetFix: vi.fn(), fix: vi.fn() } }
})

const quick: SetupFindings = {
  pending: false, failed: null, rows: 100, columns: 3, fixed: [], language: 'en', checked: true, insights: [],
  health: [{ id: 'empty:imported:0', tone: 'warning', kind: 'empty', column: 'imported', what: '73% of “imported” is empty.',
             why: 'w', todo: 'd', action: { kind: 'fill', column: 'imported', label: 'Treat empty as “Unknown”', rule: undefined } }],
}

beforeEach(() => vi.clearAllMocks())

describe('DatasetHealth', () => {
  it('any dataset (an upload) gets the quick plain health and can be fixed', async () => {
    vi.mocked(setupApi.findings).mockResolvedValue({ findings: null, source_id: null })
    vi.mocked(setupApi.datasetHealth).mockResolvedValue(quick)
    vi.mocked(setupApi.datasetFix).mockResolvedValue({ steps: [] })
    const onChanged = vi.fn()
    render(<MemoryRouter><DatasetHealth datasetId={5} onChanged={onChanged} /></MemoryRouter>)
    expect(await screen.findByText('73% of “imported” is empty.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Treat empty as “Unknown”' }))
    await waitFor(() => expect(setupApi.datasetFix).toHaveBeenCalledWith(5, quick.health[0].action, 'en'))
    expect(onChanged).toHaveBeenCalled()
    expect(await screen.findByRole('button', { name: 'Done' })).toBeDisabled()
  })

  it('prefers the guided setup findings, fixed through the setup', async () => {
    vi.mocked(setupApi.findings).mockResolvedValue({ findings: quick, source_id: 38 })
    vi.mocked(setupApi.fix).mockResolvedValue({ findings: quick })
    render(<MemoryRouter><DatasetHealth datasetId={5} dataSourceId={38} /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Treat empty as “Unknown”' }))
    await waitFor(() => expect(setupApi.fix).toHaveBeenCalledWith(38, 5, 'empty:imported:0', 'fix', 'en'))
    expect(setupApi.datasetHealth).not.toHaveBeenCalled()
  })

  it('offers the deeper guided check for a connection dataset not yet set up', async () => {
    vi.mocked(setupApi.findings).mockResolvedValue({ findings: null, source_id: null })
    vi.mocked(setupApi.datasetHealth).mockResolvedValue(quick)
    render(<MemoryRouter><DatasetHealth datasetId={5} dataSourceId={38} /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /deeper checks/ })).toHaveAttribute('href', '/setup/38')
  })

  it('stays away when nothing can be read', async () => {
    vi.mocked(setupApi.findings).mockRejectedValue(new Error('x'))
    vi.mocked(setupApi.datasetHealth).mockRejectedValue(new Error('x'))
    const { container } = render(<MemoryRouter><DatasetHealth datasetId={5} /></MemoryRouter>)
    await waitFor(() => expect(setupApi.datasetHealth).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})

describe('missing values read as Empty', () => {
  it.each(['nan', 'NaN', 'None', 'NaT', '<NA>', '', null, undefined])('%s is missing', v => {
    expect(isMissingLabel(v)).toBe(true)
  })
  it.each(['No', '0', 'Cairo'])('%s is a value', v => expect(isMissingLabel(v)).toBe(false))
})
