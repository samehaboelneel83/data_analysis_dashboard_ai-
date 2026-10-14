/**
 * The formulas each "What do you want to make?" form writes. The same strings
 * are run against the real evaluator in backend/tests/test_calc_formula_help.py
 * (TestTemplateFormulas), so a form can never write a formula the server rejects.
 */
import { describe, it, expect } from 'vitest'
import {
  bandsProblem, buildBands, buildClean, buildDate, buildLabel, buildMath, buildText, colRef, pyStr,
} from './calcTemplates'
import type { CondNode } from './conditionTree'

describe('safe pieces', () => {
  it('a typed label can never end its string early', () => {
    expect(pyStr("it's")).toBe("'it\\'s'")
    expect(pyStr('a\\')).toBe("'a\\\\'")
  })
  it('odd column names go in backticks', () => {
    expect(colRef('revenue')).toBe('revenue')
    expect(colRef('السعر')).toBe('السعر')
    expect(colRef('net revenue')).toBe('`net revenue`')
    expect(colRef('2024 sales')).toBe('`2024 sales`')
  })
})

describe('calculate from two columns', () => {
  it('writes the arithmetic, guarding every division', () => {
    expect(buildMath({ a: 'revenue', op: 'sub', bKind: 'column', b: 'cost' }))
      .toEqual({ expression: 'revenue - cost', name: 'revenue_minus_cost' })
    expect(buildMath({ a: 'revenue', op: 'div', bKind: 'column', b: 'units' })!.expression)
      .toBe('IF(units == 0, None, revenue / units)')
    expect(buildMath({ a: 'revenue', op: 'pct_change', bKind: 'column', b: 'target' })!.expression)
      .toBe('IF(target == 0, None, (revenue - target) / target * 100)')
    expect(buildMath({ a: 'price', op: 'mul', bKind: 'number', b: '1.14' })!.expression).toBe('price * 1.14')
  })
  it('waits for a complete form, and never divides by a typed 0', () => {
    expect(buildMath({ a: 'revenue', op: 'sub', bKind: 'column', b: '' })).toBeNull()
    expect(buildMath({ a: 'revenue', op: 'div', bKind: 'number', b: '0' })).toBeNull()
    expect(buildMath({ a: 'revenue', op: 'add', bKind: 'number', b: 'abc' })).toBeNull()
  })
})

describe('bands', () => {
  const form = { column: 'price', bands: [{ below: '500000', label: 'Budget' }, { below: '1500000', label: 'Mid' }],
    elseLabel: 'Luxury', emptyLabel: '' }
  it('nests IFs from the lowest band up', () => {
    expect(buildBands(form)!.expression)
      .toBe("IF(price < 500000, 'Budget', IF(price < 1500000, 'Mid', 'Luxury'))")
  })
  it('puts empty values in their own band when asked', () => {
    expect(buildBands({ ...form, emptyLabel: 'Unknown' })!.expression)
      .toBe("IF(isnull(price), 'Unknown', IF(price < 500000, 'Budget', IF(price < 1500000, 'Mid', 'Luxury')))")
  })
  it('says why it cannot be built', () => {
    expect(bandsProblem({ ...form, bands: [{ below: '9', label: 'a' }, { below: '3', label: 'b' }] })).toBe('notAscending')
    expect(bandsProblem({ ...form, elseLabel: '' })).toBe('needLabels')
    expect(bandsProblem({ ...form, bands: [{ below: 'x', label: 'a' }] })).toBe('needLimits')
  })
})

describe('label rows by conditions', () => {
  const row = (column: string, op: string, value: string): CondNode =>
    ({ kind: 'row', id: column + op + value, table: '', column, op: op as never, value })
  it('turns the boxes into IF ... else, numbers bare and text quoted', () => {
    const built = buildLabel({
      name: 'deal', elseLabel: 'Normal',
      rules: [
        { id: '1', joiner: 'and', label: 'Hot', conds: [row('condition', 'eq', 'Used'),
          { kind: 'group', id: 'g', joiner: 'or', items: [row('make', 'eq', 'Kia'), row('make', 'in', 'Hyundai, MG')] }] },
        { id: '2', joiner: 'and', label: 'Cheap', conds: [row('price', 'lt', '300000')] },
      ],
    }, new Set(['price']))
    expect(built!.expression).toBe(
      "IF(condition == 'Used' and (make == 'Kia' or (make == 'Hyundai' or make == 'MG')), 'Hot', " +
      "IF(price < 300000, 'Cheap', 'Normal'))")
  })
  it('skips unfinished conditions and needs an "otherwise" label', () => {
    const rules = [{ id: '1', joiner: 'and' as const, label: 'X', conds: [row('make', 'eq', '')] }]
    expect(buildLabel({ name: 'n', elseLabel: 'Y', rules }, new Set())).toBeNull()
  })
})

describe('text, dates and cleaning', () => {
  it('combines columns with a separator', () => {
    expect(buildText({ parts: ['make', 'model'], separator: ' ' })!.expression).toBe("CONCAT(make, ' ', model)")
    expect(buildText({ parts: ['make'], separator: ' ' })).toBeNull()
  })
  it('takes a part of a date', () => {
    expect(buildDate({ column: 'listed_at', part: 'MONTHNAME' })).toEqual({ expression: 'MONTHNAME(listed_at)', name: 'listed_at_monthname' })
  })
  it('cleans text', () => {
    expect(buildClean({ column: 'city', action: 'TRIM', find: '', replaceWith: '' })!.expression).toBe('TRIM(city)')
    expect(buildClean({ column: 'city', action: 'REPLACE', find: "'", replaceWith: '' })!.expression).toBe("REPLACE(city, '\\'', '')")
  })
})
