import { describe, it, expect, vi, beforeEach } from 'vitest'

const addText = vi.fn()
const addImage = vi.fn()
const addSlide = vi.fn(() => ({ addText, addImage }))
const writeFile = vi.fn().mockResolvedValue(undefined)
const defineLayout = vi.fn()
const made: { layout: string }[] = []

vi.mock('pptxgenjs', () => ({
  default: class { layout = ''; addSlide = addSlide; writeFile = writeFile; defineLayout = defineLayout
    constructor() { made.push(this) } },
}))

import { exportPrintViewToPptx } from './pptExport'

function buildDom() {
  document.body.innerHTML = `
    <section class="print-page"><h2>Page 1</h2>
      <div data-print-canvas>
        <div data-print-widget><span>Revenue</span> 8,632,597</div>
        <div data-print-widget><svg></svg></div>
      </div>
    </section>
    <section class="print-page"><h2>Page 2</h2>
      <div data-print-canvas><div data-print-widget>Only text</div></div>
    </section>`
  // jsdom rects are all zero-size; give the canvases geometry so placement runs
  for (const el of document.querySelectorAll('[data-print-canvas], [data-print-widget]')) {
    ;(el as HTMLElement).getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600, x: 0, y: 0, toJSON: () => ({}) })
  }
}

beforeEach(() => { vi.clearAllMocks(); made.length = 0; buildDom() })

describe('exportPrintViewToPptx', () => {
  it('makes one slide per print page and writes the file', async () => {
    const n = await exportPrintViewToPptx('Quarterly Review', document.body)
    expect(n).toBe(2)
    expect(addSlide).toHaveBeenCalledTimes(2)
    expect(writeFile).toHaveBeenCalledWith({ fileName: 'Quarterly Review.pptx' })
  })

  it('renders text widgets as text boxes; failed SVG rasterisation falls back to text', async () => {
    // jsdom cannot rasterise SVG, so the svg widget must fall back rather than vanish
    await exportPrintViewToPptx('R', document.body)
    const texts = addText.mock.calls.map(c => c[0])
    expect(texts).toContain('Page 1')
    expect(texts.some((t: string) => String(t).includes('8,632,597'))).toBe(true)
    expect(addImage).not.toHaveBeenCalled()
  })

  it('sanitises the file name', async () => {
    await exportPrintViewToPptx('bad/name:*?.pptx', document.body)
    expect(writeFile).toHaveBeenCalledWith({ fileName: 'badnamepptx.pptx' })
  })

  it('C-21: pages that share a fixed size get slides of that shape', async () => {
    for (const c of document.querySelectorAll('[data-print-canvas]')) c.setAttribute('data-page-frame', '960x720')
    await exportPrintViewToPptx('R', document.body)
    expect(defineLayout).toHaveBeenCalledTimes(1)
    const { name, width, height } = defineLayout.mock.calls[0][0]
    expect(made[0].layout).toBe(name)
    // the content box below the title keeps 4:3
    expect((width - 0.6) / (height - 0.6 - 0.6)).toBeCloseTo(960 / 720, 1)
  })

  it('C-21: flowing pages keep the widescreen slide', async () => {
    await exportPrintViewToPptx('R', document.body)
    expect(defineLayout).not.toHaveBeenCalled()
    expect(made[0].layout).toBe('LAYOUT_WIDE')
  })
})
