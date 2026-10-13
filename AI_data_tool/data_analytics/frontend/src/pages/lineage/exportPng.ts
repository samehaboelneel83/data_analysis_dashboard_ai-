import { CW, NH, WIDTH, type LNode, type Layout, type Model } from './model'

/**
 * Export as PNG (step 11), on the client: the graph as it is laid out -- the
 * cards, their names and the edges, focus and fading included -- drawn as one
 * SVG with the theme's colours resolved, then painted onto a canvas at twice
 * the size. Only what is on the page: no server call.
 */
export function lineageSvg(model: Model, cols: LNode[][], lay: Layout, edgePaths: { d: string; on: boolean; dim: boolean; dashed: boolean; bad: boolean }[],
  lit: Set<string> | null, colours: Record<string, string>, heads: string[]): string {
  const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))
  const H = lay.height
  const parts: string[] = [`<rect width="${WIDTH}" height="${H}" fill="${colours.bg}"/>`]
  heads.forEach((h, c) => parts.push(`<text x="${lay.x(c as 0 | 1 | 2)}" y="30" font-size="12" font-weight="700" fill="${colours.muted}">${esc(h)}</text>`))
  for (const e of edgePaths) {
    const stroke = e.on ? colours.accent : e.bad ? colours.danger : colours.edge
    parts.push(`<path d="${e.d}" fill="none" stroke="${stroke}" stroke-width="${e.on ? 2.2 : 1.4}"${e.dashed || e.bad ? ' stroke-dasharray="4 3"' : ''} opacity="${e.dim ? 0.15 : 1}"/>`)
  }
  for (const n of cols.flat()) {
    if (!lay.visible[n.key]) continue
    const x = lay.x(n.col), y = lay.y[n.key]
    const on = lit?.has(n.key)
    const op = lit && !on ? 0.15 : 1
    const name = n.name.length > 30 ? n.name.slice(0, 29) + '…' : n.name
    parts.push(`<g opacity="${op}"><rect x="${x}" y="${y}" width="${CW}" height="${NH}" rx="12" fill="${colours.surface}" stroke="${on ? colours.accent : colours.border}" stroke-width="${on ? 2 : 1}"/>`
      + `<text x="${x + 14}" y="${y + 34}" font-size="13.5" fill="${colours.text}">${esc(name)}</text></g>`)
  }
  // A folded column's "+ N more" row, where its edges end.
  for (const m of lay.more) {
    if (!m.hidden) continue
    parts.push(`<rect x="${lay.x(m.col)}" y="${m.y}" width="${CW}" height="40" rx="12" fill="${colours.surface}" stroke="${colours.edge}" stroke-dasharray="4 3"/>`
      + `<text x="${lay.x(m.col) + CW / 2}" y="${m.y + 25}" font-size="13" font-weight="600" text-anchor="middle" fill="${colours.muted}">+ ${m.hidden}</text>`)
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${H}" viewBox="0 0 ${WIDTH} ${H}" font-family="${esc(colours.font)}">${parts.join('')}</svg>`
}

export async function downloadPng(svg: string, filename: string): Promise<void> {
  const img = new Image()
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
  try {
    await new Promise<void>((ok, fail) => { img.onload = () => ok(); img.onerror = () => fail(new Error('svg')); img.src = url })
    const canvas = document.createElement('canvas')
    canvas.width = img.width * 2; canvas.height = img.height * 2
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas')
    ctx.scale(2, 2); ctx.drawImage(img, 0, 0)
    const blob = await new Promise<Blob | null>(r => canvas.toBlob(r, 'image/png'))
    if (!blob) throw new Error('png')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = filename
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  } finally { URL.revokeObjectURL(url) }
}
