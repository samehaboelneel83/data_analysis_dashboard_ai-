/**
 * Rasterise a live chart SVG to a PNG data URL.
 *
 * Computed theme colours are inlined first: the SVG references CSS custom
 * properties (var(--accent)) that do not exist inside an isolated image
 * document, which would silently render every themed element black. Shared by
 * the per-widget "Export as image" action and the PowerPoint exporter.
 */
export async function svgToPngDataUrl(svg: SVGSVGElement, scale = 2): Promise<string> {
  const clone = svg.cloneNode(true) as SVGSVGElement
  const styled = document.defaultView!.getComputedStyle(svg)
  clone.style.backgroundColor = styled.backgroundColor === 'rgba(0, 0, 0, 0)'
    ? getComputedStyle(document.body).backgroundColor
    : styled.backgroundColor
  const live = svg.querySelectorAll<SVGElement>('*')
  clone.querySelectorAll<SVGElement>('*').forEach((el, i) => {
    const cs = document.defaultView!.getComputedStyle(live[i])
    if (cs.fill && cs.fill !== 'none') el.setAttribute('fill', cs.fill)
    if (cs.stroke && cs.stroke !== 'none') el.setAttribute('stroke', cs.stroke)
  })
  const box = svg.getBoundingClientRect()
  const xml = new XMLSerializer().serializeToString(clone)
  const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('svg rasterisation failed'))
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(box.width * scale))
    canvas.height = Math.max(1, Math.round(box.height * scale))
    const g = canvas.getContext('2d')
    if (!g) throw new Error('no 2d context')
    g.fillStyle = clone.style.backgroundColor || '#ffffff'
    g.fillRect(0, 0, canvas.width, canvas.height)
    g.drawImage(img, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/png')
  } finally {
    URL.revokeObjectURL(url)
  }
}
