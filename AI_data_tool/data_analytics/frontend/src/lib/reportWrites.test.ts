import { describe, it, expect } from 'vitest'
import { reportWritten } from './reportWrites'

describe('C-17: which report a request wrote to', () => {
  it.each([
    ['patch', '/reports/5', 5],
    ['post', '/reports/5/pages', 5],
    ['delete', '/reports/12/pages/3/widgets/9', 12],
    ['put', 'reports/7/classification', 7],
    ['post', '/reports/5?x=1', 5],
  ])('%s %s -> %s', (method, url, id) => {
    expect(reportWritten({ method, url })).toBe(id)
  })
  it.each([
    ['get', '/reports/5'],
    ['post', '/reports'],
    ['post', '/reports/duplicate'],
    ['patch', '/datasets/5'],
  ])('%s %s -> none', (method, url) => {
    expect(reportWritten({ method, url })).toBeNull()
  })
})
