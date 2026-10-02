import { describe, expect, it } from 'vitest'
import { cleanDatasets } from './cleanDatasets'
import { looksLikeTestData } from './testData'

const ds = (id: number, name: string, extra: Record<string, unknown> = {}) =>
  ({ id, name, column_meta: {}, created_by: null, ...extra }) as never

describe('clean lists for newcomers (4.7)', () => {
  it('flags what the HR evaluation found', () => {
    for (const n of ['13', '2', 'kjhkjhkjhkjh', 'claude job check', 'x', 'sss', 'report_pagessss',
                     'data-1777154203914', 'Metrics Snapshot Test', 'ss output', 'ggf output'])
      expect(looksLikeTestData(n)).toBe(true)
    for (const n of ['Current workforce', 'Salaries 2026', 'HR', 'Route planning extract output',
                     'Demo — Sales', 'Olist_order_items', 'Joined dataset', 'Enrolments 2025'])
      expect(looksLikeTestData(n)).toBe(false)
  })

  it('hides test-looking names, puts certified first, and counts what it hid', () => {
    const list = [ds(1, '13'), ds(2, 'Salaries'), ds(3, 'Current workforce', { column_meta: { __certified__: { by: 1 } } }),
                  ds(4, 'kjhkjhkjhkjh', { created_by: 7 })]
    const got = cleanDatasets(list, 'all', 7, false)
    expect(got.visible.map((d: { id: number }) => d.id)).toEqual([3, 2])
    expect(got.hiddenTest).toBe(2)
    expect(got.certified).toBe(1)
    expect(got.mine).toBe(1)
    expect(cleanDatasets(list, 'certified', 7, false).visible.map((d: { id: number }) => d.id)).toEqual([3])
    expect(cleanDatasets(list, 'mine', 7, true).visible.map((d: { id: number }) => d.id)).toEqual([4])
  })

  it('never hides a certified dataset, whatever it is called', () => {
    const got = cleanDatasets([ds(1, 'test HR', { column_meta: { __certified__: {} } })], 'all', null, false)
    expect(got.visible).toHaveLength(1)
  })
})
