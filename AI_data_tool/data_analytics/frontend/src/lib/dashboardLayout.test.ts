import { describe, it, expect } from 'vitest'
import {
  applyRecipe,
  compact,
  dropPacked,
  dropFree,
  minSize,
  overlaps,
  resizeFree,
  resizePacked,
  RECIPES,
} from './dashboardLayout'
import type { LayoutItem } from './dashboardLayout'

function item(id: number, type: string, layout = { x: 0, y: 0, w: 6, h: 5 }): LayoutItem {
  return { id, widget_type: type, layout }
}

function mapOf(items: LayoutItem[]) {
  return Object.fromEntries(items.map(i => [i.id, i.layout]))
}

function withLayouts(items: LayoutItem[], layouts: Record<number, { x: number; y: number; w: number; h: number }>): LayoutItem[] {
  return items.map(i => ({ ...i, layout: layouts[i.id] ?? i.layout }))
}

function assertNoOverlap(layouts: Record<number, { x: number; y: number; w: number; h: number }>) {
  const list = Object.values(layouts)
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length; j++) {
      expect(overlaps(list[i], list[j]), `overlap ${JSON.stringify(list[i])} vs ${JSON.stringify(list[j])}`).toBe(false)
    }
  }
}

describe('minSize', () => {
  it('gives KPIs a small strip size and charts / tables enough room to read', () => {
    expect(minSize('kpi')).toEqual({ w: 3, h: 2 })
    expect(minSize('bar').w).toBeGreaterThanOrEqual(4)
    expect(minSize('bar').h).toBeGreaterThanOrEqual(4)
    expect(minSize('table').w).toBeGreaterThanOrEqual(6)
  })
})

describe('applyRecipe executive', () => {
  it('is the default recipe in the gallery', () => {
    expect(RECIPES[0].id).toBe('executive')
  })

  it('puts KPIs on the top strip, the lone chart as a full-width hero, and the table below — no holes or overlap', () => {
    const items = [
      item(1, 'kpi', { x: 8, y: 10, w: 3, h: 3 }),
      item(2, 'kpi', { x: 0, y: 12, w: 3, h: 3 }),
      item(3, 'bar', { x: 0, y: 0, w: 4, h: 4 }),
      item(4, 'table', { x: 2, y: 4, w: 4, h: 3 }),
    ]
    const next = applyRecipe(items, 'executive')
    assertNoOverlap(next)
    expect(compact(withLayouts(items, next))).toEqual(next)

    expect(next[1].y).toBe(0)
    expect(next[2].y).toBe(0)
    expect(next[1].w + next[2].w).toBe(12)
    expect(next[3].y).toBe(next[1].h)
    expect(next[3].w).toBe(12)
    expect(next[4].w).toBe(12)
    expect(next[4].y).toBe(next[3].y + next[3].h)
  })

  it('collapses unused slots when there are fewer widgets than the recipe draws', () => {
    const next = applyRecipe([item(1, 'bar')], 'executive')
    expect(next[1]).toEqual({ x: 0, y: 0, w: 12, h: 6 })
  })

  it('wraps extra charts to a two-across row at min readable width', () => {
    const items = [item(1, 'bar'), item(2, 'line'), item(3, 'pie')]
    const next = applyRecipe(items, 'executive')
    assertNoOverlap(next)
    expect(next[1].w).toBe(8)
    expect(next[2].w).toBe(4)
    expect(next[3].y).toBe(next[1].y + next[1].h)
    expect(next[3].w).toBeGreaterThanOrEqual(minSize('pie').w)
  })
})

describe('compact', () => {
  it('closes vertical holes and keeps x', () => {
    const items = [
      item(1, 'bar', { x: 0, y: 8, w: 6, h: 4 }),
      item(2, 'bar', { x: 6, y: 8, w: 6, h: 4 }),
    ]
    const map = compact(items)
    expect(map[1]).toEqual({ x: 0, y: 0, w: 6, h: 4 })
    expect(map[2]).toEqual({ x: 6, y: 0, w: 6, h: 4 })
  })
})

describe('dropPacked', () => {
  it('swaps two tiles when one is dropped onto the other', () => {
    const items = [
      item(1, 'bar', { x: 0, y: 0, w: 6, h: 5 }),
      item(2, 'line', { x: 6, y: 0, w: 6, h: 5 }),
    ]
    const next = dropPacked(items, 1, { x: 6, y: 0 })
    expect(next[1].x).toBe(6)
    expect(next[2].x).toBe(0)
    assertNoOverlap(next)
  })

  it('shifts and compacts when dropped onto a gap', () => {
    const items = [
      item(1, 'bar', { x: 0, y: 0, w: 6, h: 5 }),
      item(2, 'line', { x: 0, y: 5, w: 6, h: 5 }),
    ]
    const next = dropPacked(items, 2, { x: 6, y: 0 })
    expect(next[2].x).toBe(6)
    expect(next[2].y).toBe(0)
    expect(next[1].y).toBe(0)
    assertNoOverlap(next)
  })
})

describe('resizePacked', () => {
  it('will not shrink a chart below its readable min size', () => {
    const items = [item(1, 'bar', { x: 0, y: 0, w: 8, h: 6 })]
    const next = resizePacked(items, 1, 1, 1)
    expect(next[1].w).toBeGreaterThanOrEqual(minSize('bar').w)
    expect(next[1].h).toBeGreaterThanOrEqual(minSize('bar').h)
  })

  it('pushes neighbors down instead of overlapping when a tile grows', () => {
    const items = [
      item(1, 'bar', { x: 0, y: 0, w: 12, h: 4 }),
      item(2, 'table', { x: 0, y: 4, w: 12, h: 5 }),
    ]
    const next = resizePacked(items, 1, 12, 8)
    expect(next[1].h).toBe(8)
    expect(next[2].y).toBeGreaterThanOrEqual(8)
    assertNoOverlap(next)
  })
})

describe('dropFree / resizeFree', () => {
  it('refuses to overlap: the dropped tile lands in the nearest free cell', () => {
    const items = [
      item(1, 'bar', { x: 0, y: 0, w: 6, h: 5 }),
      item(2, 'line', { x: 6, y: 0, w: 6, h: 5 }),
    ]
    const next = dropFree(items, 1, { x: 6, y: 0 })
    expect(overlaps(next[1], next[2])).toBe(false)
    expect(next[1].x).toBeGreaterThanOrEqual(0)
    expect(next[1].x + next[1].w).toBeLessThanOrEqual(12)
  })

  it('will not shrink past min size in free mode either', () => {
    const items = [item(1, 'table', { x: 0, y: 0, w: 8, h: 6 })]
    const next = resizeFree(items, 1, 1, 1)
    expect(next[1].w).toBeGreaterThanOrEqual(minSize('table').w)
    expect(next[1].h).toBeGreaterThanOrEqual(minSize('table').h)
  })
})

describe('recipes', () => {
  it('packs every gallery recipe without overlap or overflow', () => {
    const items = [
      item(1, 'kpi'), item(2, 'kpi'), item(3, 'kpi'),
      item(4, 'bar'), item(5, 'line'), item(6, 'pie'),
      item(7, 'table'), item(8, 'map_choropleth'),
    ]
    for (const recipe of RECIPES) {
      const next = applyRecipe(items, recipe.id)
      assertNoOverlap(next)
      for (const [id, l] of Object.entries(next)) {
        expect(l.x).toBeGreaterThanOrEqual(0)
        expect(l.x + l.w).toBeLessThanOrEqual(12)
        expect(l.y).toBeGreaterThanOrEqual(0)
        const type = items.find(i => i.id === Number(id))!.widget_type
        expect(l.w).toBeGreaterThanOrEqual(minSize(type).w)
        expect(l.h).toBeGreaterThanOrEqual(minSize(type).h)
      }
    }
  })
})
