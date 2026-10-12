import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import RuleRoles, { ruleRoles, type Rule } from './RuleRoles'
import ModelRenderer from './ModelRenderer'
import { modelOptsConfig, seedModelOpts } from '../ModelSettings'

// p leads to q and q back to p; p leads to r; s leads to q.
const rules: Rule[] = [
  { if_items: [['a', 'p']], then_items: [['b', 'q']], lift: 2.1, confidence: 0.8, support_pct: 26.6 },
  { if_items: [['b', 'q']], then_items: [['a', 'p']], lift: 2.1, confidence: 0.7, support_pct: 26.6 },
  { if_items: [['a', 'p']], then_items: [['c', 'r']], lift: 1.5, confidence: 0.6, support_pct: 12.0 },
  { if_items: [['d', 's']], then_items: [['b', 'q']], lift: 1.2, confidence: 0.5, support_pct: 8.0 },
]

describe('association rules read by role', () => {
  it('gives each value its role and its relation to every other', () => {
    const by = Object.fromEntries(ruleRoles(rules).map(i => [i.id, i]))
    expect(by['a=p'].role).toBe('B')                    // both ways with q, one way to r
    expect(by['c=r'].role).toBe('C')
    expect(by['d=s'].role).toBe('A')
    expect(by['a=p'].partners).toEqual({ 'b=q': 'B', 'c=r': 'A' })
    expect(by['b=q'].partners).toEqual({ 'a=p': 'B', 'd=s': 'C' })
    expect([by['a=p'].starts, by['a=p'].ends, by['a=p'].rules]).toEqual([2, 1, 3])
  })

  it('counts a link reported both ways as one-way when one direction is clearly the surer', () => {
    const lopsided: Rule[] = [
      { if_items: [['a', 'p']], then_items: [['b', 'q']], lift: 2, confidence: 0.9 },
      { if_items: [['b', 'q']], then_items: [['a', 'p']], lift: 2, confidence: 0.3 },
    ]
    const by = Object.fromEntries(ruleRoles(lopsided).map(i => [i.id, i]))
    expect(by['a=p'].partners).toEqual({ 'b=q': 'A' })
    expect([by['a=p'].role, by['b=q'].role]).toEqual(['A', 'C'])
    // ...and as both ways when they are close.
    const even = lopsided.map((r, i) => ({ ...r, confidence: i ? 0.8 : 0.9 }))
    expect(ruleRoles(even).map(i => i.role)).toEqual(['B', 'B'])
  })

  it('draws the network with a node per value, coloured by role, and counts the roles', () => {
    render(<RuleRoles rules={rules} view="network" />)
    expect(screen.getAllByTestId('role-node').map(n => n.getAttribute('data-role')).sort()).toEqual(['A', 'B', 'B', 'C'])
    // One line per linked pair: an arrow for the two one-way links, a plain line for the two-way one.
    expect(screen.getAllByTestId('role-link').map(l => l.getAttribute('data-role')).sort()).toEqual(['A', 'A', 'B'])
    expect(screen.getByTestId('role-legend').textContent).toContain('Antecedent (A) 1')
  })

  it('draws the matrix: the row towards the column', () => {
    render(<RuleRoles rules={rules} view="matrix" />)
    const cells = [...screen.getByTestId('rule-roles-matrix').querySelectorAll('td')]
    expect(cells.filter(c => c.getAttribute('data-role') === 'B')).toHaveLength(2)      // p–q and q–p
    expect(cells.filter(c => c.getAttribute('data-role') === 'A')).toHaveLength(2)      // p→r, s→q
    expect(cells.filter(c => c.getAttribute('data-role') === 'C')).toHaveLength(2)
  })

  it('draws the summary, the table and the chord from the same rules', () => {
    const { rerender } = render(<RuleRoles rules={rules} view="summary" />)
    expect(screen.getAllByTestId('role-bar')).toHaveLength(4)
    rerender(<RuleRoles rules={rules} view="table" />)
    const table = screen.getByTestId('rule-roles-table')
    expect(table.querySelectorAll('tbody tr')).toHaveLength(4)
    expect(table.textContent).toContain('p → q')
    expect(table.textContent).toContain('2.10×')
    rerender(<RuleRoles rules={rules} view="chord" />)
    expect(screen.getAllByTestId('chord-arc')).toHaveLength(4)
    expect(screen.getAllByTestId('chord-ribbon')).toHaveLength(3)                       // p–q once, p–r, s–q
  })

  it('shows only the most connected values of a long list and says so', () => {
    render(<RuleRoles rules={rules} view="summary" limit={2} />)
    expect(screen.getAllByTestId('role-bar')).toHaveLength(2)
    expect(screen.getByText('The 2 most connected of 4 values.')).toBeInTheDocument()
  })

  it('is one view of the rules widget, chosen in its settings', () => {
    const data = { type: 'model', status: 'ok', model: 'rules', variables: ['a', 'b'], rules, network: { nodes: [], edges: [] },
      result: {}, population: { rows_used: 100, rows_total: 100 }, fit: { name: 'strongest lift', value: 2.1 } }
    render(<ModelRenderer data={data as never} cfg={{ rules_view: 'chord' } as never} rows={[]} rtl={false} broadcasts={false}
      localSelected={null} onClickPoint={() => {}} />)
    expect(screen.getByTestId('rule-roles-chord')).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(seedModelOpts(modelOptsConfig('model_rules', { rules_view: 'matrix', rules_items: 8 }))).toEqual({ rules_view: 'matrix', rules_items: 8 })
    expect(modelOptsConfig('model_rules', {})).toEqual({})
  })
})
