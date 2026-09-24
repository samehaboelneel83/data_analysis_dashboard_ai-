/**
 * Marching squares: the isolines of a regular grid at one level, as line
 * segments in grid coordinates (x = column, y = row). Small and dependency-
 * free; the map projects the segments itself.
 */
export type Seg = [[number, number], [number, number]]

export function isolines(values: readonly number[], nx: number, ny: number, level: number): Seg[] {
  const v = (x: number, y: number) => values[y * nx + x]
  const lerp = (a: number, b: number) => (a === b ? 0.5 : (level - a) / (b - a))
  const segs: Seg[] = []
  for (let y = 0; y < ny - 1; y++) {
    for (let x = 0; x < nx - 1; x++) {
      const a = v(x, y), b = v(x + 1, y), c = v(x + 1, y + 1), d = v(x, y + 1)
      const idx = (a >= level ? 1 : 0) | (b >= level ? 2 : 0) | (c >= level ? 4 : 0) | (d >= level ? 8 : 0)
      if (idx === 0 || idx === 15) continue
      // Edge crossing points: bottom (a-b), right (b-c), top (d-c), left (a-d).
      const B: [number, number] = [x + lerp(a, b), y]
      const R: [number, number] = [x + 1, y + lerp(b, c)]
      const T: [number, number] = [x + lerp(d, c), y + 1]
      const L: [number, number] = [x, y + lerp(a, d)]
      switch (idx) {
        case 1: case 14: segs.push([L, B]); break
        case 2: case 13: segs.push([B, R]); break
        case 3: case 12: segs.push([L, R]); break
        case 4: case 11: segs.push([R, T]); break
        case 6: case 9: segs.push([B, T]); break
        case 7: case 8: segs.push([L, T]); break
        // Saddles: resolved by the cell's centre value, the usual convention.
        case 5: {
          const centre = (a + b + c + d) / 4
          if (centre >= level) { segs.push([L, T]); segs.push([B, R]) } else { segs.push([L, B]); segs.push([R, T]) }
          break
        }
        case 10: {
          const centre = (a + b + c + d) / 4
          if (centre >= level) { segs.push([L, B]); segs.push([R, T]) } else { segs.push([L, T]); segs.push([B, R]) }
          break
        }
      }
    }
  }
  return segs
}
