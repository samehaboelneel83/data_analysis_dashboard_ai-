import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import SankeyChartRenderer from './SankeyChartRenderer'

/** C-08: the Sankey drew ribbons and bars with no names, all one colour. */
const data = {
  nodes: [{ name: 'Europe' }, { name: 'Asia' }, { name: 'Hardware' }, { name: 'Software' }],
  links: [{ source: 0, target: 2, value: 10 }, { source: 1, target: 3, value: 6 }, { source: 0, target: 3, value: 4 }],
}
const base = { rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {} } as any

describe('SankeyChartRenderer (C-08)', () => {
  it('labels every node', () => {
    const { container } = render(<SankeyChartRenderer {...base} data={data} plotW={600} plotH={300} />)
    const texts = [...container.querySelectorAll('svg text')].map(t => t.textContent)
    for (const n of ['Europe', 'Asia', 'Hardware', 'Software']) expect(texts.join('|')).toContain(n)
  })
  it('colours each flow by its source', () => {
    const { container } = render(<SankeyChartRenderer {...base} data={data} plotW={600} plotH={300} />)
    const strokes = [...container.querySelectorAll('path[data-sankey-link]')].map(p => p.getAttribute('stroke'))
    expect(strokes).toHaveLength(3)
    expect(new Set(strokes).size).toBe(2)          // Europe's two flows share a colour, Asia's differs
  })
})
