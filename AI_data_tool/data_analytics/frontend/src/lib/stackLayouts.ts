/**
 * F-15: where several new widgets go when they are added at once -- one under
 * another, below everything already on the page, in the order given. Each
 * call of the one-at-a-time path measured the page from the same snapshot,
 * so a loop of them stacked every widget at the same `y`.
 */
export interface Box { x: number; y: number; w: number; h: number }

export function stackBelow(existing: Box[], sizes: { w: number; h: number }[]): Box[] {
  let y = existing.length ? Math.max(...existing.map(l => l.y + l.h)) : 0
  return sizes.map(s => {
    const box = { x: 0, y, w: s.w, h: s.h }
    y += s.h
    return box
  })
}
