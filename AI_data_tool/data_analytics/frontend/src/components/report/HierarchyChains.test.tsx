import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import HierarchyChains, { chainsOf, moved } from './HierarchyChains'
import type { HierarchyNode } from '../../types/report'
import { DirectionProvider } from '../../contexts/DirectionContext'

const node = (id: number, parent_id: number | null, name: string, node_type: string, column_name: string | null, format: string | null = null, position = 0) =>
  ({ id, dataset_id: 1, parent_id, name, node_type, column_name, format, position }) as HierarchyNode

// What auto-generate builds: a Dates folder holding "Order Date" and its
// Year > Quarter > Month > Week > Date chain, and a Geography folder
// holding Continent > Country > City.
const nodes: HierarchyNode[] = [
  node(1, null, 'Dates', 'folder', null),
  node(2, 1, 'Order Date', 'date', 'order_date'),
  node(3, 2, 'Year', 'date', 'order_date', 'year'),
  node(4, 3, 'Quarter', 'date', 'order_date', 'quarter'),
  node(5, 4, 'Month', 'date', 'order_date', 'month'),
  node(6, 5, 'Week', 'date', 'order_date', 'week'),
  node(7, 6, 'Date', 'date', 'order_date', 'day'),
  node(10, null, 'Geography', 'folder', null, null, 1),
  node(11, 10, 'Continent', 'dimension', 'continent'),
  node(12, 11, 'Country', 'dimension', 'country'),
  node(13, 12, 'City', 'dimension', 'city'),
  // A plain column in a folder: no levels below, so no chain.
  node(20, 1, 'Ship Date', 'date', 'ship_date'),
]

describe('chainsOf', () => {
  it('finds the date chain titled by its column and the geography chain', () => {
    const chains = chainsOf(nodes)
    expect(chains.map(c => [c.title, c.kind, c.levels.map(l => l.name)])).toEqual([
      ['Order Date', 'date', ['Year', 'Quarter', 'Month', 'Week', 'Date']],
      ['Geography', 'geography', ['Continent', 'Country', 'City']],
    ])
    expect(chains.map(c => c.anchor)).toEqual([2, 10])
  })

  it('moved puts one level at a new index', () => {
    expect(moved(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b'])
    expect(moved(['a', 'b', 'c'], 0, 1)).toEqual(['b', 'a', 'c'])
  })
})

describe('the hierarchy tree', () => {
  const setup = (over: Partial<Parameters<typeof HierarchyChains>[0]> = {}) => {
    const props = { nodes, isChecked: () => false, onToggle: vi.fn(), onReorder: vi.fn(), canEdit: true, ...over }
    render(<HierarchyChains {...props} />)
    return props
  }

  it('nests each level under the one before it, with a checkbox each', () => {
    setup()
    const list = screen.getByRole('list', { name: 'Order Date levels' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows.map(r => r.getAttribute('data-level'))).toEqual(['Year', 'Quarter', 'Month', 'Week', 'Date'])
    const indents = rows.map(r => parseInt(r.style.paddingInlineStart))
    expect(indents).toEqual([...indents].sort((a, b) => a - b))
    expect(new Set(indents).size).toBe(5)
    expect(screen.getByRole('checkbox', { name: 'Select Geography Country' })).toBeInTheDocument()
  })

  it('a ticked level stages as its token', () => {
    const p = setup({ isChecked: t => t === 'h:5' })
    expect(screen.getByRole('checkbox', { name: 'Select Order Date Month' })).toBeChecked()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Geography City' }))
    expect(p.onToggle).toHaveBeenCalledWith('h:13')
  })

  it('the arrows move a level up or down the chain, whole chain in one call', () => {
    const p = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Move City up' }))
    expect(p.onReorder).toHaveBeenCalledWith([11, 13, 12])
    fireEvent.click(screen.getByRole('button', { name: 'Move Year down' }))
    expect(p.onReorder).toHaveBeenLastCalledWith([4, 3, 5, 6, 7])
    expect(screen.getByRole('button', { name: 'Move Year up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move Date down' })).toBeDisabled()
  })

  it('dragging a level onto another reorders the chain', () => {
    const p = setup()
    const list = screen.getByRole('list', { name: 'Geography levels' })
    const [continent, , city] = within(list).getAllByRole('listitem')
    const dt = { setData: vi.fn(), getData: vi.fn(), effectAllowed: '', dropEffect: '' }
    fireEvent.dragStart(continent, { dataTransfer: dt })
    fireEvent.dragOver(city, { dataTransfer: dt })
    fireEvent.drop(city, { dataTransfer: dt })
    expect(p.onReorder).toHaveBeenCalledWith([12, 13, 11])
  })

  it('a drag across chains does nothing', () => {
    const p = setup()
    const year = screen.getByRole('list', { name: 'Order Date levels' }).querySelector('li')!
    const city = within(screen.getByRole('list', { name: 'Geography levels' })).getAllByRole('listitem')[2]
    const dt = { setData: vi.fn(), getData: vi.fn(), effectAllowed: '', dropEffect: '' }
    fireEvent.dragStart(year, { dataTransfer: dt })
    fireEvent.drop(city, { dataTransfer: dt })
    expect(p.onReorder).not.toHaveBeenCalled()
  })

  it('a viewer sees the tree and ticks, but cannot reorder', () => {
    setup({ canEdit: false })
    expect(screen.getByRole('checkbox', { name: 'Select Order Date Year' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Move .* up/ })).toBeNull()
  })

  it('a chain folds under its title', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Geography/ }))
    expect(screen.queryByRole('list', { name: 'Geography levels' })).toBeNull()
  })

  it('clicking a level name binds it when a widget is selected', () => {
    const onPick = vi.fn()
    setup({ onPick })
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 5, format: 'month' }))
  })
})

describe('the hierarchy tree in Arabic (QA5b S5)', () => {
  it('says its screen-reader labels and tooltips in Arabic, with the names isolated', () => {
    localStorage.setItem('datalytics.language', 'ar')
    render(<DirectionProvider><HierarchyChains nodes={nodes} isChecked={() => false} onToggle={vi.fn()} onReorder={vi.fn()} onPick={vi.fn()} canEdit /></DirectionProvider>)
    expect(screen.getByRole('list', { name: 'مستويات «⁨Geography⁩»' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'تحديد «⁨Country⁩» من «⁨Geography⁩»' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'نقل «⁨Country⁩» لأعلى' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'نقل «⁨Country⁩» لأسفل' })).toBeInTheDocument()
    expect(screen.getByTitle('استخدام «⁨Country⁩» في العنصر المحدد')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Move|Select/ })).toBeNull()
    localStorage.removeItem('datalytics.language')
  })
})
