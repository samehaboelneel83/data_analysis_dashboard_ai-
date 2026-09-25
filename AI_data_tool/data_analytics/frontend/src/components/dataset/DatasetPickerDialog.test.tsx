import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DatasetPickerDialog, { orderDatasets, rememberDataset, readRecentDatasetIds, sizeLabel } from './DatasetPickerDialog'
import type { Dataset } from '../../services/api'

const ds = (id: number, name: string, extra: Partial<Dataset> = {}) =>
  ({ id, name, row_count: 10, col_count: 3, file_size: 1, created_at: '', mode: 'import', ...extra }) as Dataset

describe('orderDatasets', () => {
  it('puts recently used first, then the rest by name (numbers in number order)', () => {
    const all = [ds(1, 'Zeta'), ds(2, 'alpha'), ds(3, 'Beta 10'), ds(4, 'Beta 9')]
    const { recent, rest } = orderDatasets(all, [3], '')
    expect(recent.map(d => d.id)).toEqual([3])
    expect(rest.map(d => d.name)).toEqual(['alpha', 'Beta 9', 'Zeta'])
  })
  it('search narrows both lists', () => {
    const { recent, rest } = orderDatasets([ds(1, 'Sales'), ds(2, 'HR')], [2], 'sal')
    expect(recent).toEqual([])
    expect(rest.map(d => d.name)).toEqual(['Sales'])
  })
})

describe('recents', () => {
  beforeEach(() => localStorage.clear())
  it('remembers picks, most recent first, without duplicates', () => {
    rememberDataset(1); rememberDataset(2); rememberDataset(1)
    expect(readRecentDatasetIds()).toEqual([1, 2])
  })
})

describe('sizeLabel', () => {
  it('a DirectQuery dataset is "live", never "0 rows"', () => {
    expect(sizeLabel(ds(1, 'x', { mode: 'directquery', row_count: 0 }))).toMatch(/^live query/)
  })
})

describe('DatasetPickerDialog', () => {
  beforeEach(() => localStorage.clear())
  it('picking a dataset reports it and remembers it', () => {
    const onPick = vi.fn()
    render(<DatasetPickerDialog datasets={[ds(5, 'Demo — Sales')]} onPick={onPick} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Demo — Sales/ }))
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 5 }))
    expect(readRecentDatasetIds()).toEqual([5])
  })
  it('an excluded (already attached) dataset is not offered', () => {
    render(<DatasetPickerDialog datasets={[ds(5, 'A'), ds(6, 'B')]} excludeIds={[5]} onPick={() => {}} onClose={() => {}} />)
    expect(screen.queryByRole('button', { name: /^A/ })).toBeNull()
    expect(screen.getByRole('button', { name: /^B/ })).toBeTruthy()
  })
  it('says so when there is no data at all', () => {
    render(<DatasetPickerDialog datasets={[]} onPick={() => {}} onClose={() => {}} />)
    expect(screen.getByText(/no datasets yet/i)).toBeTruthy()
  })
})

describe('same-named datasets (BUG-027)', () => {
  it('tells two datasets with one name apart by id, and leaves a unique name alone', () => {
    render(<DatasetPickerDialog datasets={[ds(7, 'Sales'), ds(9, 'Sales'), ds(4, 'HR')]}
      onPick={vi.fn()} onClose={vi.fn()} />)
    const names = screen.getAllByRole('button').map(b => b.textContent ?? '')
    expect(names.some(t => t.includes('Sales #7'))).toBe(true)
    expect(names.some(t => t.includes('Sales #9'))).toBe(true)
    expect(names.some(t => t.includes('HR #'))).toBe(false)
  })
})
