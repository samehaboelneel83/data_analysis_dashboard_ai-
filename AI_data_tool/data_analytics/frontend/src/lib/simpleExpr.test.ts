import { describe, it, expect } from 'vitest'
import { compileRow, compileSimple, emptyConditionRow } from './simpleExpr'
import type { SimpleExprState } from './simpleExpr'

describe('simpleExpr', () => {
  it('compiles a literal comparison row', () => {
    expect(compileRow({ type: 'condition', column: 'region', op: 'eq', valueKind: 'literal', value: 'North' }))
      .toBe('region == "North"')
  })

  it('compiles a numeric literal unquoted', () => {
    expect(compileRow({ type: 'condition', column: 'salary', op: 'gt', valueKind: 'literal', value: '20000' }))
      .toBe('salary > 20000')
  })

  it('compiles a column-to-column comparison', () => {
    expect(compileRow({ type: 'condition', column: 'a', op: 'ne', valueKind: 'column', value: 'b' }))
      .toBe('a != b')
  })

  it('compiles a system-parameter row', () => {
    expect(compileRow({ type: 'condition', column: 'owner', op: 'eq', valueKind: 'system', value: 'USEREMAIL()' }))
      .toBe('owner == USEREMAIL()')
  })

  it('compiles isnull/notnull without a value', () => {
    expect(compileRow({ type: 'condition', column: 'x', op: 'isnull', valueKind: 'literal', value: '' }))
      .toBe('isnull(x) == True')
    expect(compileRow({ type: 'condition', column: 'x', op: 'notnull', valueKind: 'literal', value: '' }))
      .toBe('isnull(x) == False')
  })

  it('backtick-quotes column names with spaces', () => {
    expect(compileRow({ type: 'condition', column: 'first name', op: 'eq', valueKind: 'literal', value: 'a' }))
      .toBe('`first name` == "a"')
  })

  it('returns empty for an incomplete condition row', () => {
    expect(compileRow(emptyConditionRow('region'))).toBe('')
  })

  it('compiles a function row with named args', () => {
    expect(compileRow({ type: 'function', fn: 'round', args: ['salary', '2'] })).toBe('round(salary, 2)')
  })

  it('returns empty for a function row with no args', () => {
    expect(compileRow({ type: 'function', fn: 'round', args: ['', ''] })).toBe('')
  })

  it('joins multiple rows with AND', () => {
    const state: SimpleExprState = {
      joiner: 'and',
      rows: [
        { type: 'condition', column: 'region', op: 'eq', valueKind: 'literal', value: 'North' },
        { type: 'condition', column: 'owner', op: 'eq', valueKind: 'system', value: 'USEREMAIL()' },
      ],
    }
    expect(compileSimple(state)).toBe('region == "North" and owner == USEREMAIL()')
  })

  it('joins multiple rows with OR', () => {
    const state: SimpleExprState = {
      joiner: 'or',
      rows: [
        { type: 'condition', column: 'region', op: 'eq', valueKind: 'literal', value: 'North' },
        { type: 'condition', column: 'region', op: 'eq', valueKind: 'literal', value: 'South' },
      ],
    }
    expect(compileSimple(state)).toBe('region == "North" or region == "South"')
  })

  it('skips incomplete rows when compiling the whole set', () => {
    const state: SimpleExprState = {
      joiner: 'and',
      rows: [emptyConditionRow('region'), { type: 'condition', column: 'owner', op: 'eq', valueKind: 'literal', value: 'me' }],
    }
    expect(compileSimple(state)).toBe('owner == "me"')
  })

  it('compiles to empty string when every row is incomplete', () => {
    expect(compileSimple({ joiner: 'and', rows: [emptyConditionRow('region')] })).toBe('')
  })
})
