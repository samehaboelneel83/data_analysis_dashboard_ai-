import { describe, it, expect } from 'vitest'
import { answerSource } from './ChatPane'

/** Part IV criterion 10: every AI answer names its engine and its evidence. */
describe('where an Ask AI answer came from', () => {
  const r = (total: number, source?: 'query' | 'catalog') =>
    ({ step: 's', columns: [], rows: [], total, truncated: false, source })

  it('a queried answer names the queries and the rows', () => {
    expect(answerSource({ intent: 'query', results: [r(2000)], sql: ['select 1'], presentation: null }))
      .toBe('AI answer from 1 query on your data (2,000 rows); "Show SQL" shows exactly what ran')
  })

  it('a reply with no query says so', () => {
    expect(answerSource({ intent: 'chat', results: [], presentation: null }))
      .toBe('AI reply: no data was queried for this')
  })

  it('a catalog answer is not passed off as a query result', () => {
    expect(answerSource({ intent: 'query', results: [r(5, 'catalog')], presentation: null }))
      .toMatch(/data catalog/)
  })
})
