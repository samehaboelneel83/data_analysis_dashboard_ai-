import { describe, it, expect, beforeEach } from 'vitest'
import { savePending, clearPending, readPending, PENDING_MAX_AGE_MS } from './pendingEdits'

describe('pending-edit journal', () => {
  beforeEach(() => localStorage.clear())
  it('an edit that was never sent is found again', () => {
    savePending(7, { dimension: 'region' }, 'Sales')
    const got = readPending([7, 8])
    expect(got).toHaveLength(1)
    expect(got[0]).toMatchObject({ widgetId: 7, title: 'Sales', config: { dimension: 'region' } })
  })
  it('a sent edit leaves no trace', () => {
    savePending(7, {}, 'x'); clearPending(7)
    expect(readPending([7])).toEqual([])
  })
  it('only the widgets asked about', () => {
    savePending(1, {}, 'a'); savePending(2, {}, 'b')
    expect(readPending([2]).map(e => e.widgetId)).toEqual([2])
  })
  it('stale entries expire and are removed', () => {
    savePending(3, {}, 'old')
    const later = Date.now() + PENDING_MAX_AGE_MS + 1
    expect(readPending([3], later)).toEqual([])
    expect(localStorage.getItem('datalytics:pending-widget:3')).toBeNull()
  })
  it('garbage in storage never throws', () => {
    localStorage.setItem('datalytics:pending-widget:4', '{not json')
    expect(readPending([4])).toEqual([])
  })
})
