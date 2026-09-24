import type { Widget } from '../types/report'

type Layout = Widget['layout']
type LayoutMap = Record<number, Layout>
type Patch = Record<number, Partial<Layout>>

export function alignWidgets(layouts: LayoutMap, mode: 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom'): Patch {
  const entries = Object.entries(layouts).map(([id, l]) => [Number(id), l] as const)
  const patch: Patch = {}
  if (mode === 'left' || mode === 'center' || mode === 'right') {
    const lefts = entries.map(([, l]) => l.x)
    const rights = entries.map(([, l]) => l.x + l.w)
    const target = mode === 'left' ? Math.min(...lefts) : mode === 'right' ? Math.max(...rights) : Math.round((Math.min(...lefts) + Math.max(...rights)) / 2)
    for (const [id, l] of entries) {
      patch[id] = { x: mode === 'right' ? target - l.w : mode === 'center' ? target - Math.round(l.w / 2) : target }
    }
  } else {
    const tops = entries.map(([, l]) => l.y)
    const bottoms = entries.map(([, l]) => l.y + l.h)
    const target = mode === 'top' ? Math.min(...tops) : mode === 'bottom' ? Math.max(...bottoms) : Math.round((Math.min(...tops) + Math.max(...bottoms)) / 2)
    for (const [id, l] of entries) {
      patch[id] = { y: mode === 'bottom' ? target - l.h : mode === 'middle' ? target - Math.round(l.h / 2) : target }
    }
  }
  return patch
}

export function distributeWidgets(layouts: LayoutMap, axis: 'horizontal' | 'vertical'): Patch {
  const entries = Object.entries(layouts).map(([id, l]) => [Number(id), l] as const)
  const key = axis === 'horizontal' ? 'x' : 'y'
  const sorted = [...entries].sort((a, b) => a[1][key] - b[1][key])
  if (sorted.length < 3) {
    // Nothing to distribute with fewer than 3 widgets — the first/last already anchor the ends.
    return {}
  }
  const first = sorted[0][1][key]
  const last = sorted[sorted.length - 1][1][key]
  const step = (last - first) / (sorted.length - 1)
  const patch: Patch = {}
  sorted.forEach(([id], i) => { patch[id] = { [key]: Math.round(first + step * i) } as Partial<Layout> })
  return patch
}
