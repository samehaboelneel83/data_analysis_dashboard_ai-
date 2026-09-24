/**
 * Greedy label offsets so city names on a network map do not print on top
 * of each other. Preferred spot is the incoming (x, y); collisions walk
 * up, then to the side, until they clear or the attempt budget runs out.
 */
export type LabelAnchor = { id: string; x: number; y: number; text: string }

export function placeLabels(
  anchors: LabelAnchor[],
  charW = 6.2,
  lineH = 12,
  pad = 3,
): Record<string, { x: number; y: number }> {
  const placed: { x: number; y: number; w: number }[] = []
  const out: Record<string, { x: number; y: number }> = {}

  const overlaps = (x: number, y: number, w: number) =>
    placed.some(p =>
      Math.abs(x - p.x) * 2 < w + p.w + pad && Math.abs(y - p.y) < lineH + pad)

  for (const a of anchors) {
    const w = Math.max(14, a.text.length * charW)
    let x = a.x
    let y = a.y
    const shifts: [number, number][] = [
      [0, 0],
      [0, -(lineH + 2)],
      [0, -(lineH + 2) * 2],
      [w * 0.55, 0],
      [-(w * 0.55), 0],
      [w * 0.55, -(lineH + 2)],
      [-(w * 0.55), -(lineH + 2)],
      [0, lineH + 4],
      [w * 0.7, lineH + 4],
      [-(w * 0.7), lineH + 4],
      [0, -(lineH + 2) * 3],
      [w * 0.9, -(lineH + 2) * 2],
    ]
    for (const [dx, dy] of shifts) {
      x = a.x + dx
      y = a.y + dy
      if (!overlaps(x, y, w)) break
    }
    placed.push({ x, y, w })
    out[a.id] = { x, y }
  }
  return out
}
