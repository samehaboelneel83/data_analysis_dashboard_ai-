import { describe, it, expect } from 'vitest'
import { compileConditionRow, compileWhere, sqlLiteral, type SqlConditionRow } from './sqlWhere'

describe('sqlLiteral', () => {
  it('leaves numbers bare', () => {
    expect(sqlLiteral('42')).toBe('42')
    expect(sqlLiteral('3.5')).toBe('3.5')
  })
  it('quotes and escapes strings, doubling embedded single quotes', () => {
    expect(sqlLiteral('US')).toBe("'US'")
    expect(sqlLiteral("O'Brien's")).toBe("'O''Brien''s'")
  })
})

describe('compileConditionRow', () => {
  it('compiles comparisons with the right operator and quoting', () => {
    expect(compileConditionRow({ column: 'region', op: 'eq', value: 'US' })).toBe("region = 'US'")
    expect(compileConditionRow({ column: 'amount', op: 'gte', value: '100' })).toBe('amount >= 100')
  })
  it('compiles is_null / not_null with no value needed', () => {
    expect(compileConditionRow({ column: 'region', op: 'is_null', value: '' })).toBe('region IS NULL')
    expect(compileConditionRow({ column: 'region', op: 'not_null', value: '' })).toBe('region IS NOT NULL')
  })
  it('compiles contains as a LIKE with escaped wild-wrapped value', () => {
    expect(compileConditionRow({ column: 'name', op: 'contains', value: "O'Brien" }))
      .toBe("name LIKE '%O''Brien%'")
  })
  it('compiles in as a quoted, comma-split list', () => {
    expect(compileConditionRow({ column: 'region', op: 'in', value: 'US, CA' }))
      .toBe("region IN ('US', 'CA')")
  })
  it('returns empty for an unfinished row -- no column or no value yet', () => {
    expect(compileConditionRow({ column: '', op: 'eq', value: 'US' })).toBe('')
    expect(compileConditionRow({ column: 'region', op: 'eq', value: '' })).toBe('')
  })
})

describe('compileWhere', () => {
  const rows: SqlConditionRow[] = [
    { column: 'region', op: 'eq', value: 'US' },
    { column: 'amount', op: 'gte', value: '100' },
  ]
  it('joins rows with AND', () => {
    expect(compileWhere(rows, 'and')).toBe("region = 'US' AND amount >= 100")
  })
  it('joins rows with OR', () => {
    expect(compileWhere(rows, 'or')).toBe("region = 'US' OR amount >= 100")
  })
  it('skips unfinished rows when compiling the whole set', () => {
    const withGap: SqlConditionRow[] = [...rows, { column: 'segment', op: 'eq', value: '' }]
    expect(compileWhere(withGap, 'and')).toBe("region = 'US' AND amount >= 100")
  })
  it('returns empty for no complete rows', () => {
    expect(compileWhere([], 'and')).toBe('')
    expect(compileWhere([{ column: '', op: 'eq', value: '' }], 'and')).toBe('')
  })
})
