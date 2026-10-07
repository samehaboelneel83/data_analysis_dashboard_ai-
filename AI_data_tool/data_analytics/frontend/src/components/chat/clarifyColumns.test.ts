import { describe, it, expect } from 'vitest'
import { columnsMentioned } from './clarifyColumns'

/**
 * QA B3 (7-QA): the model's questions back name columns in plain words, not
 * only in bold, code or quotes -- "the highest revenue, the highest margin"
 * on Demo — Sales -- and no chips were offered. Plain whole-word mentions
 * count too, and a column's first word stands for it when no other column
 * starts the same way ("margin" -> margin_pct).
 */
describe('plain-text mentions (QA B3)', () => {
  const cols = ['date', 'region', 'country', 'product', 'revenue', 'cost', 'margin_pct', 'units', 'unit_price']
  it('finds columns named in plain words, in the reply\'s order', () => {
    expect(columnsMentioned('Do you mean the items with the highest revenue, the highest margin, or another specific metric?', cols))
      .toEqual(['revenue', 'margin_pct'])
  })
  it('does not guess when the first word is shared', () => {
    expect(columnsMentioned('Which unit do you mean?', [...cols, 'unit_cost'])).toEqual([])
  })
  it('matches a whole word only, never part of one', () => {
    expect(columnsMentioned('Do you want the costliest products or the regional view?', cols)).toEqual([])
  })
  it('still puts set-apart terms first', () => {
    expect(columnsMentioned('By **country**, or by revenue?', cols)).toEqual(['country', 'revenue'])
  })
  it('says nothing when no column is named', () => {
    expect(columnsMentioned('Do you mean to calculate the average of a specific metric grouped by a specific dimension?', cols)).toEqual([])
  })
})
