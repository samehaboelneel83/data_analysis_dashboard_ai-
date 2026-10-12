import { describe, it, expect } from 'vitest'
import { ambiguousDate, guessType, nameFromFile, parseDelimited, previewJson, previewOf, kindOf } from './readFile'

describe('reading a file for the preview', () => {
  it('parses quoted fields, doubled quotes and line breaks inside quotes; finds the delimiter', () => {
    expect(parseDelimited('a,b\n"x, y","say ""hi"""\n"two\nlines",3\n')).toEqual([['a', 'b'], ['x, y', 'say "hi"'], ['two\nlines', '3']])
    expect(parseDelimited('a;b\r\n1;2\r\n')).toEqual([['a', 'b'], ['1', '2']])
    expect(parseDelimited('a\tb\n1\t2')).toEqual([['a', 'b'], ['1', '2']])
  })
  it('guesses kinds from the values, and spots day/month dates that could go either way', () => {
    expect(guessType(['1', '2,300', '-4.5', ''])).toBe('num')
    expect(guessType(['2025-09-01', '2025-09-02'])).toBe('date')
    expect(guessType(['yes', 'No'])).toBe('bool')
    expect(guessType(['a', '1'])).toBe('text')
    expect(ambiguousDate(['05/09/2025', '06/09/2025'])).toBe(true)
    expect(ambiguousDate(['05/09/2025', '25/09/2025'])).toBe(false)
    expect(ambiguousDate(['2025-09-05'])).toBe(false)
  })
  it('builds the preview: names, first rows, empty cells; JSON records too', () => {
    const p = previewOf([['id', ''], ['1', ''], ['2', 'x']], true)
    expect(p.columns).toEqual(['id', 'column_2'])
    expect(p.total).toBe(2)
    expect(p.missing).toBe(1)
    expect(previewJson('[{"a":1,"b":{"c":2}},{"a":2}]')!.rows).toEqual([['1', '{"c":2}'], ['2', '']])
    expect(previewJson('not json')).toBeNull()
  })
  it('names and kinds', () => {
    expect(nameFromFile('enrolments_2025.csv')).toBe('Enrolments 2025')
    expect(kindOf('a.ACCDB')).toBe('access')
    expect(kindOf('b.tsv')).toBe('csv')
  })
})
