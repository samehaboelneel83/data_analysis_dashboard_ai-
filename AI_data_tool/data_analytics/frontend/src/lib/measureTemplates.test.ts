/** The formulas the measure forms write; the same strings run on the real
 *  engine in backend/tests/test_calc_formula_help.py (TestMeasureTemplateFormulas). */
import { describe, it, expect } from 'vitest'
import { buildOnly, buildRatio, buildShare, buildSummary } from './measureTemplates'
import type { CondNode } from './conditionTree'

describe('measure forms', () => {
  it('summarise a column', () => {
    expect(buildSummary({ how: 'MAX', column: 'price' })).toEqual({ expression: 'MAX(price)', name: 'Highest price' })
    expect(buildSummary({ how: 'SUM', column: '' })).toBeNull()
  })

  it('compare two totals, every division guarded', () => {
    expect(buildRatio({ howA: 'SUM', a: 'revenue', op: 'div', howB: 'SUM', b: 'cost' })!.expression)
      .toBe('IF(SUM(cost) == 0, None, SUM(revenue) / SUM(cost))')
    expect(buildRatio({ howA: 'SUM', a: 'revenue', op: 'pct_change', howB: 'SUM', b: 'target' })!.expression)
      .toBe('IF(SUM(target) == 0, None, (SUM(revenue) - SUM(target)) / SUM(target) * 100)')
    expect(buildRatio({ howA: 'MAX', a: 'revenue', op: 'diff', howB: 'MIN', b: 'revenue' })!.expression)
      .toBe('MAX(revenue) - MIN(revenue)')
  })

  it('share of the total', () => {
    expect(buildShare({ how: 'SUM', column: 'revenue' })!.expression)
      .toBe('IF(TOTAL(SUM(revenue)) == 0, None, SUM(revenue) / TOTAL(SUM(revenue)) * 100)')
  })

  it('only some rows: a total adds 0, an average leaves the row out', () => {
    const conds: CondNode[] = [{ kind: 'row', id: 'a', table: '', column: 'channel', op: 'eq', value: 'On' }]
    expect(buildOnly({ how: 'SUM', column: 'revenue', joiner: 'and', conds, name: '' }, new Set())!.expression)
      .toBe("SUM(IF(channel == 'On', revenue, 0))")
    expect(buildOnly({ how: 'AVG', column: 'revenue', joiner: 'and', conds, name: '' }, new Set())!.expression)
      .toBe("AVG(IF(channel == 'On', revenue, None))")
    expect(buildOnly({ how: 'ROWS', column: '', joiner: 'and', conds, name: '' }, new Set())!.expression)
      .toBe("SUM(IF(channel == 'On', 1, 0))")
    expect(buildOnly({ how: 'SUM', column: 'revenue', joiner: 'and', conds: [], name: '' }, new Set())).toBeNull()
  })
})
