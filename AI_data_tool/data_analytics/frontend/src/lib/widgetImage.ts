/**
 * Rasterise a live chart SVG to a PNG data URL.
 *
 * Computed theme colours are inlined first: the SVG references CSS custom
 * properties (var(--accent)) that do not exist inside an isolated image
 * document, which would silently render every themed element black. Shared by
 * the per-widget "Export as image" action and the PowerPoint exporter.
 */

/**
 * The chart in a widget, not the first `<svg>` in it (E15).
 *
 * The header's ⋮ menu and other controls are icons drawn as SVG, and they come
 * before the chart in the DOM: "Export as image" used to save a 15px ⋮. Icons
 * (`.lucide`), anything in a menu or the header controls are skipped; of the
 * rest the largest wins (a chart with a small inline glyph), the first when
 * nothing has a size (no layout, as in tests).
 */
export function pickChartSvg(root: ParentNode | null | undefined): SVGSVGElement | null {
  if (!root) return null
  const all = Array.from(root.querySelectorAll<SVGSVGElement>('svg')).filter(svg =>
    !svg.classList.contains('lucide') && !svg.closest('.dl-whead__ctl, [role="menu"], button')
    && !(svg.parentElement?.closest('svg')))
  if (!all.length) return null
  let best = all[0], bestArea = -1
  for (const svg of all) {
    const r = svg.getBoundingClientRect()
    const area = r.width * r.height
    if (area > bestArea) { best = svg; bestArea = area }
  }
  return best
}

type Fetcher = (href: string) => Promise<Blob>

const defaultFetcher: Fetcher = async href => {
  const r = await fetch(href, { mode: 'cors', credentials: 'omit' })
  if (!r.ok) throw new Error(`tile ${r.status}`)
  return r.blob()
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result))
    fr.onerror = () => reject(fr.error ?? new Error('read failed'))
    fr.readAsDataURL(blob)
  })
}

/**
 * An SVG drawn as an image cannot load anything from outside it, so a map's
 * basemap tiles (`<image href="https://tiles…">`) came out as blank squares.
 * Each external image is fetched and inlined as a data URL; one the tile
 * server will not share (no CORS) is removed, and the count of those is
 * returned so the caller can say the basemap is missing rather than ship a
 * half-drawn map in silence.
 */
export async function inlineExternalImages(clone: SVGSVGElement, fetcher: Fetcher = defaultFetcher): Promise<number> {
  const images = Array.from(clone.querySelectorAll('image'))
  const cache = new Map<string, Promise<string | null>>()
  let dropped = 0
  await Promise.all(images.map(async img => {
    const href = img.getAttribute('href') ?? img.getAttribute('xlink:href') ?? ''
    if (!href || href.startsWith('data:')) return
    if (!cache.has(href)) {
      cache.set(href, fetcher(href).then(blobToDataUrl).catch(() => null))
    }
    const data = await cache.get(href)!
    if (data) {
      img.setAttribute('href', data)
      img.removeAttribute('xlink:href')
    } else {
      img.remove()
      dropped++
    }
  }))
  return dropped
}

/** The clone, styled to stand alone: theme colours resolved (into the style
 *  too when the element's own style names a variable, since a style beats an
 *  attribute), and a pixel size, since `width="100%"` has nothing to be a
 *  percentage of inside an image. */
export function standaloneClone(svg: SVGSVGElement): SVGSVGElement {
  const clone = svg.cloneNode(true) as SVGSVGElement
  const styled = document.defaultView!.getComputedStyle(svg)
  clone.style.backgroundColor = styled.backgroundColor === 'rgba(0, 0, 0, 0)'
    ? getComputedStyle(document.body).backgroundColor
    : styled.backgroundColor
  const live = svg.querySelectorAll<SVGElement>('*')
  clone.querySelectorAll<SVGElement>('*').forEach((el, i) => {
    const cs = document.defaultView!.getComputedStyle(live[i])
    const viaStyle = (el.getAttribute('style') ?? '').includes('var(')
    if (cs.fill && cs.fill !== 'none') {
      el.setAttribute('fill', cs.fill)
      if (viaStyle) el.style.setProperty('fill', cs.fill)
    }
    if (cs.stroke && cs.stroke !== 'none') {
      el.setAttribute('stroke', cs.stroke)
      if (viaStyle) el.style.setProperty('stroke', cs.stroke)
    }
  })
  const box = svg.getBoundingClientRect()
  if (box.width > 0 && box.height > 0) {
    clone.setAttribute('width', String(Math.round(box.width)))
    clone.setAttribute('height', String(Math.round(box.height)))
  }
  return clone
}

/** The PNG, and how many external images (basemap tiles) could not be put
 *  in it. */
export async function svgToPng(svg: SVGSVGElement, scale = 2,
                               fetcher: Fetcher = defaultFetcher): Promise<{ dataUrl: string; dropped: number }> {
  const clone = standaloneClone(svg)
  const dropped = await inlineExternalImages(clone, fetcher)
  return { dataUrl: await rasterise(svg, clone, scale), dropped }
}

export async function svgToPngDataUrl(svg: SVGSVGElement, scale = 2): Promise<string> {
  return (await svgToPng(svg, scale)).dataUrl
}

async function rasterise(svg: SVGSVGElement, clone: SVGSVGElement, scale: number): Promise<string> {
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
