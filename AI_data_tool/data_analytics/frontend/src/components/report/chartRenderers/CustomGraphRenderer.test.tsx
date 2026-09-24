/**
 * A chart the author composed from layers.
 *
 * The catalogue had three fixed combinations; this draws whatever the author
 * built. What the renderer must not do is quietly simplify that: a layer the
 * author added has to appear, on the axis they put it on, drawn as the mark
 * they chose.
 *
 * jsdom has no layout, so Recharts draws its marks but reports zero for
 * everything measured. These assertions are about WHICH elements exist and what
 * they are bound to — never their geometry, which is not real here.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import CustomGraphRenderer from './CustomGraphRenderer'

beforeAll(() => {
  // recharts draws nothing inside a 0x0 ResponsiveContainer, and jsdom measures
  // everything as 0x0 — so without this every assertion below passes vacuously
  // against an empty chart. Same polyfill the dual-axis tests use.
  Element.prototype.getBoundingClientRect = () => ({
    width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const props = (data: unknown) => ({
  rows: [], data, cfg: {}, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: vi.fn(),
})

const twoLayers = {
  type: 'custom_graph',
  rows: [{ name: 'N', s0: 30, s1: 15 }, { name: 'S', s0: 20, s1: 10 }],
  layers: [
    { key: 's0', label: 'sum of revenue', mark: 'bar', axis: 'left', measure: 'revenue', aggregation: 'sum' },
    { key: 's1', label: 'avg of revenue', mark: 'line', axis: 'right', measure: 'revenue', aggregation: 'avg' },
  ],
}

describe('CustomGraphRenderer', () => {
  it('draws a mark per layer', () => {
    const { container } = render(<CustomGraphRenderer {...props(twoLayers)} />)
    // Recharts tags its series by type; a composed chart that rendered only the
    // first layer would still look like a chart.
    expect(container.querySelector('.recharts-bar')).not.toBeNull()
    expect(container.querySelector('.recharts-line')).not.toBeNull()
  })

  it('gives a right-axis layer a second axis to sit on', () => {
    // Putting a count and an average on one scale is the misreading a dual axis
    // exists to prevent, so an author asking for the right axis must get one.
    const { container } = render(<CustomGraphRenderer {...props(twoLayers)} />)
    expect(container.querySelectorAll('.recharts-yAxis').length).toBe(2)
  })

  it('uses one axis when every layer shares it', () => {
    const { container } = render(<CustomGraphRenderer {...props({
      ...twoLayers,
      layers: twoLayers.layers.map(l => ({ ...l, axis: 'left' })),
    })} />)
    expect(container.querySelectorAll('.recharts-yAxis').length).toBe(1)
  })

  it('names each layer so the legend can tell them apart', () => {
    // Both layers read the same column. A legend saying "revenue" twice tells
    // the reader nothing about which line is the average.
    //
    // Queried inside the LEGEND: a layer alone on its axis now also titles
    // that axis, so its name is on the chart twice, and a bare getByText
    // could no longer tell which one it had found.
    const { container } = render(<CustomGraphRenderer {...props(twoLayers)} />)
    const legend = container.querySelector('.recharts-legend-wrapper')
    expect(legend).toHaveTextContent('sum of revenue')
    expect(legend).toHaveTextContent('avg of revenue')
  })

  it('titles an axis that carries exactly one layer', () => {
    // The reader should not have to match a line to a legend entry to learn
    // what the scale beside it counts.
    const { container } = render(<CustomGraphRenderer {...props(twoLayers)} />)
    const axisTitles = [...container.querySelectorAll('.recharts-label')]
      .map(el => el.textContent)
    expect(axisTitles).toContain('sum of revenue')
    expect(axisTitles).toContain('avg of revenue')
  })

  it('leaves an axis untitled when two layers share it', () => {
    // Two measures on one scale have no single name, and titling it after one
    // of them would state something false about the other. The legend is what
    // tells them apart there.
    const shared = {
      ...twoLayers,
      layers: (twoLayers.layers as { axis?: string }[]).map(l => ({ ...l, axis: 'left' })),
    }
    const { container } = render(<CustomGraphRenderer {...props(shared)} />)
    const axisTitles = [...container.querySelectorAll('.recharts-label')]
      .map(el => el.textContent)
    expect(axisTitles).not.toContain('sum of revenue')
    expect(axisTitles).not.toContain('avg of revenue')
  })

  it('says what it could not draw', () => {
    // The shaper reports a layer whose column has gone. Swallowing that leaves
    // the author hunting a series that was never going to appear.
    render(<CustomGraphRenderer {...props({ ...twoLayers, skipped: ['gone'] })} />)
    expect(screen.getByText(/gone/)).toBeInTheDocument()
  })

  it('asks to be built when it has no layers yet', () => {
    // A freshly dropped widget is mid-task, not broken, and an empty frame with
    // no explanation is the least useful thing to show.
    render(<CustomGraphRenderer {...props({ type: 'empty', rows: [], layers: [] })} />)
    expect(screen.getByText(/add a layer/i)).toBeInTheDocument()
  })
})
