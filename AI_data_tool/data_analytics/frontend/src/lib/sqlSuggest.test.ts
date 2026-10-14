import { describe, expect, it } from 'vitest'
import { applySuggestion, suggest } from './sqlSuggest'

const tables = ['employees', 'dept_emp', 'departments', 'salaries']

describe('Browse autocomplete (4.3)', () => {
  it('"dep" suggests dept_emp and departments', () => {
    const got = suggest('SELECT * FROM dep', 17, tables, {}).map(s => s.insert)
    expect(got.slice(0, 2)).toEqual(['dept_emp', 'departments'])
  })

  it('suggests columns of tables the statement mentions', () => {
    const got = suggest('SELECT to_ FROM dept_emp', 9, tables, { dept_emp: ['emp_no', 'to_date', 'from_date'] })
    expect(got[0]).toMatchObject({ insert: 'to_date', kind: 'column' })
  })

  it('stays quiet for one letter', () => {
    expect(suggest('SELECT d', 8, tables, {})).toEqual([])
  })

  it('replaces only the word at the caret', () => {
    expect(applySuggestion('SELECT * FROM dep WHERE 1', 17, 'departments'))
      .toEqual({ text: 'SELECT * FROM departments WHERE 1', caret: 25 })
  })
})
