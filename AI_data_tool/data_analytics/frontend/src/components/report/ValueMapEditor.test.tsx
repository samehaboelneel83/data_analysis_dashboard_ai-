import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ValueMapEditor from './ValueMapEditor'

const rule = { id: 'r1', kind: 'value_map' as const, target: 'mark' as const, column: 'name', mappings: [] }

// `.at(-1)` is not in this project's ES2020 lib target — same conversion
// IntervalEditor.test.tsx already made.
const lastCall = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0]

describe('ValueMapEditor', () => {
  it('adds a mapping with a value and a colour', () => {
    const onChange = vi.fn()
    render(<ValueMapEditor rule={rule} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add mapping/i }))
    const emitted = lastCall(onChange)
    expect(emitted.kind).toBe('value_map')
    expect(emitted.mappings).toHaveLength(1)
  })

  it('edits a mapping value and keeps the kind', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, mappings: [{ value: '', color: '#6c8fff' }] }
    render(<ValueMapEditor rule={withOne} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/mapped value/i), { target: { value: 'EMEA' } })
    const emitted = lastCall(onChange)
    expect(emitted.mappings[0].value).toBe('EMEA')
    expect(emitted.kind).toBe('value_map')
  })

  it('toggles Any Category, which the engine reads to scan every category column', () => {
    const onChange = vi.fn()
    render(<ValueMapEditor rule={rule} onChange={onChange} />)

    fireEvent.click(screen.getByLabelText(/any category/i))
    expect(lastCall(onChange).any_category).toBe(true)
  })

  it('removes a mapping', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, mappings: [{ value: 'EMEA', color: '#6c8fff' }] }
    render(<ValueMapEditor rule={withOne} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /remove mapping/i }))
    expect(lastCall(onChange).mappings).toEqual([])
  })

  it('gives each mapping a distinct accessible name for its Remove button', () => {
    // IntervalEditor got this fix; ValueMapEditor never did. With two mappings, an
    // unindexed "Remove mapping" makes getByRole throw on the ambiguity — and a
    // screen-reader user hears the same name for every row.
    const onChange = vi.fn()
    const withTwo = {
      ...rule,
      mappings: [{ value: 'EMEA', color: '#6c8fff' }, { value: 'APAC', color: '#34d399' }],
    }
    render(<ValueMapEditor rule={withTwo} onChange={onChange} />)

    const removeButtons = screen.getAllByRole('button', { name: /remove mapping/i })
    expect(removeButtons).toHaveLength(2)
    expect(new Set(removeButtons.map(b => b.textContent)).size).toBe(2)
    expect(new Set(screen.getAllByLabelText(/mapped value/i).map(l => l.id)).size).toBe(2)

    // The second mapping's own button removes only that mapping.
    fireEvent.click(screen.getByRole('button', { name: /remove mapping 2/i }))
    expect(lastCall(onChange).mappings).toEqual([{ value: 'EMEA', color: '#6c8fff' }])
  })

  it('marks every button as type="button", the convention throughout this panel', () => {
    render(<ValueMapEditor rule={{ ...rule, mappings: [{ value: 'EMEA', color: '#6c8fff' }] }} onChange={vi.fn()} />)

    for (const button of screen.getAllByRole('button')) {
      expect(button).toHaveAttribute('type', 'button')
    }
  })
})
