/**
 * E15: "Export as image" saves the chart, with its basemap.
 */
import { describe, it, expect, vi } from 'vitest'
import { inlineExternalImages, pickChartSvg, standaloneClone } from './widgetImage'

function html(markup: string): HTMLElement {
  const div = document.createElement('div')
  div.innerHTML = markup
  document.body.appendChild(div)
  return div
}

describe('pickChartSvg', () => {
  it('skips the header menu icon that comes before the chart', () => {
    // The ⋮ in a widget header is an svg, first in the DOM: it used to be
    // what "Export as image" saved.
    const root = html(`
      <div class="dl-whead"><span class="dl-whead__ctl"><button><svg class="lucide lucide-more-vertical"></svg></button></span></div>
      <div><svg data-chart="yes"><g><svg data-inner></svg></g></svg></div>`)
    expect(pickChartSvg(root)?.getAttribute('data-chart')).toBe('yes')
  })

  it('skips a stray lucide icon outside the header too', () => {
    const root = html(`<svg class="lucide"></svg><svg data-chart="map"></svg>`)
    expect(pickChartSvg(root)?.getAttribute('data-chart')).toBe('map')
  })

  it('prefers the largest drawing when there are several', () => {
    const root = html(`<svg data-chart="glyph"></svg><svg data-chart="chart"></svg>`)
    const [glyph, chart] = Array.from(root.querySelectorAll('svg'))
    glyph.getBoundingClientRect = () => ({ width: 12, height: 12 }) as DOMRect
    chart.getBoundingClientRect = () => ({ width: 400, height: 300 }) as DOMRect
    expect(pickChartSvg(root)).toBe(chart)
  })

  it('has nothing to offer for a widget with no chart', () => {
    expect(pickChartSvg(html('<p>42</p>'))).toBeNull()
    expect(pickChartSvg(null)).toBeNull()
  })
})

describe('inlineExternalImages', () => {
  const svgWith = (...hrefs: string[]) => {
    const root = html(`<svg>${hrefs.map(h => `<image href="${h}"></image>`).join('')}</svg>`)
    return root.querySelector('svg') as SVGSVGElement
  }

  it('turns basemap tiles into data the image carries, fetching each once', async () => {
    const svg = svgWith('https://tiles.example/1/0/0.png', 'https://tiles.example/1/0/0.png', 'data:image/png;base64,AA==')
    const fetcher = vi.fn(async () => new Blob(['png'], { type: 'image/png' }))
    expect(await inlineExternalImages(svg, fetcher)).toBe(0)
    expect(fetcher).toHaveBeenCalledTimes(1)
    const hrefs = Array.from(svg.querySelectorAll('image')).map(i => i.getAttribute('href')!)
    expect(hrefs.every(h => h.startsWith('data:image/png'))).toBe(true)
  })

  it('removes a tile the server will not share, and counts it', async () => {
    const svg = svgWith('https://ok.example/a.png', 'https://nocors.example/b.png')
    const fetcher = async (href: string) => {
      if (href.includes('nocors')) throw new TypeError('Failed to fetch')
      return new Blob(['png'], { type: 'image/png' })
    }
    expect(await inlineExternalImages(svg, fetcher)).toBe(1)
    expect(svg.querySelectorAll('image')).toHaveLength(1)
  })
})

describe('standaloneClone', () => {
  it('gives the image a pixel size, since 100% of nothing is nothing', () => {
    const svg = html('<svg width="100%" height="100%" viewBox="0 0 400 300"></svg>').querySelector('svg')!
    svg.getBoundingClientRect = () => ({ width: 400.4, height: 299.6 }) as DOMRect
    const clone = standaloneClone(svg)
    expect(clone.getAttribute('width')).toBe('400')
    expect(clone.getAttribute('height')).toBe('300')
    expect(svg.getAttribute('width')).toBe('100%')
  })
})
