import { pickChartSvg, svgToPngDataUrl } from './widgetImage'

/**
 * Export the print view to PowerPoint: one widescreen slide per report page,
 * each chart widget rasterised from its live SVG and placed at its authored
 * position; text-shaped widgets (KPI, text, tables) land as text boxes with
 * their rendered content. Runs against the PRINT route's DOM because that is
 * the one place every page of the report is mounted at once.
 *
 * pptxgenjs is dynamically imported: PowerPoint export is a rare action and
 * the library has no business in the initial bundle.
 */
export async function exportPrintViewToPptx(reportName: string, root: HTMLElement): Promise<number> {
  const { default: PptxGen } = await import('pptxgenjs')
  const pres = new PptxGen()
  const TITLE_H = 0.6, MARGIN = 0.3
  const SLIDE_W = 13.33
  let SLIDE_H = 7.5

  const sections = [...root.querySelectorAll<HTMLElement>('section.print-page')]
  // C-21: pages drawn at a fixed size (data-page-frame="WxH") get slides of
  // that shape when they all share one -- a deck has a single slide size.
  // Otherwise the widescreen slide, with each fixed page kept in proportion.
  const frameOf = (sec: HTMLElement) => {
    const m = /^(\d+)x(\d+)$/.exec(sec.querySelector('[data-print-canvas]')?.getAttribute('data-page-frame') ?? '')
    return m ? { w: Number(m[1]), h: Number(m[2]) } : null
  }
  const frames = sections.map(frameOf)
  const first = frames[0]
  if (first && frames.every(f => f && f.w * first.h === f.h * first.w)) {
    const contentW = SLIDE_W - 2 * MARGIN
    SLIDE_H = Math.min(56, Math.max(1, contentW * first.h / first.w + TITLE_H + 2 * MARGIN))
    pres.defineLayout({ name: 'DL_PAGE', width: SLIDE_W, height: SLIDE_H })
    pres.layout = 'DL_PAGE'
  } else {
    pres.layout = 'LAYOUT_WIDE'                    // 13.33 x 7.5 in
  }
  for (const section of sections) {
    const slide = pres.addSlide()
    const title = section.querySelector('h2')?.textContent ?? ''
    slide.addText(title, { x: MARGIN, y: 0.1, w: SLIDE_W - 2 * MARGIN, h: TITLE_H,
      fontSize: 18, bold: true })

    const canvasBox = section.querySelector<HTMLElement>('[data-print-canvas]')
    if (!canvasBox) continue
    const sec = canvasBox.getBoundingClientRect()
    if (sec.width === 0 || sec.height === 0) continue
    let contentH = SLIDE_H - TITLE_H - 2 * MARGIN
    let contentW = SLIDE_W - 2 * MARGIN
    if (frameOf(section)) {
      // A fixed page is not stretched to the slide: same proportions as drawn.
      const k = Math.min(contentW / sec.width, contentH / sec.height)
      contentW = sec.width * k; contentH = sec.height * k
    }

    for (const node of canvasBox.querySelectorAll<HTMLElement>('[data-print-widget]')) {
      const r = node.getBoundingClientRect()
      const geom = {
        x: MARGIN + ((r.left - sec.left) / sec.width) * contentW,
        y: TITLE_H + MARGIN + ((r.top - sec.top) / sec.height) * contentH,
        w: Math.max(0.3, (r.width / sec.width) * contentW),
        h: Math.max(0.3, (r.height / sec.height) * contentH),
      }
      const svg = pickChartSvg(node)
      if (svg) {
        try {
          const data = await svgToPngDataUrl(svg, 2)
          slide.addImage({ data, ...geom })
          continue
        } catch { /* fall through to the text rendering below */ }
      }
      // Text-shaped widgets (and any chart whose rasterisation failed): their
      // rendered text, so the slide still carries the number rather than a hole.
      const text = (node.innerText ?? node.textContent ?? '').trim().slice(0, 800)
      if (text) {
        slide.addText(text, { ...geom, fontSize: 11, valign: 'top',
          fill: { color: 'F5F6F8' }, color: '222222' })
      }
    }
  }
  const safe = reportName.replace(/[^A-Za-z0-9 _-]/g, '').slice(0, 60) || 'report'
  await pres.writeFile({ fileName: `${safe}.pptx` })
  return sections.length
}
