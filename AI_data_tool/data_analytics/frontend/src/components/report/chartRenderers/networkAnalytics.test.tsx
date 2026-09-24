import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import NetworkGraphRenderer from './NetworkGraphRenderer'
import type { ChartRendererProps } from './types'

/**
 * Communities and predicted links, made visible.
 *
 * The shaper computes both, and a capability that reaches no pixel is the trap
 * this codebase has hit repeatedly — an endpoint with passing tests and no
 * caller. So these assert the RENDERER consumes them, not merely that the
 * payload carries them.
 *
 * The property worth defending hardest is the separation: a predicted link is
 * an inference, and drawing it like an observed edge would have the chart
 * assert a relationship the data does not contain.
 */

const base: Omit<ChartRendererProps, 'rows'> = {
  data: {}, cfg: {}, rtl: false, broadcasts: false, localSelected: null,
  onClickPoint: () => {},
}

const node = (id: string, community: number, x = 0.5, y = 0.5) => ({
  id, x, y, degree: 0.5, closeness: 0.5, betweenness: 0.1, reach: 1, community,
})

const DATA = {
  nodes: [node('a1', 0, 0.2, 0.2), node('a2', 0, 0.3, 0.3),
          node('b1', 1, 0.8, 0.8), node('b2', 1, 0.7, 0.7)],
  links: [{ source: 'a1', target: 'a2', value: 2 },
          { source: 'b1', target: 'b2', value: 2 }],
  suggested_links: [{ source: 'a1', target: 'b1', score: 1.4, shared_neighbours: 3 }],
  communities: 2,
}

const draw = (data: object = DATA) =>
  render(<NetworkGraphRenderer {...base} rows={[]} data={data} />)

describe('communities are visible', () => {
  it('colours nodes of different communities differently', () => {
    // The whole point of community detection is that you can SEE the grouping;
    // one accent colour for every node hides exactly what was computed.
    const { container } = draw()
    const fills = [...container.querySelectorAll('circle')].map(c => c.getAttribute('fill'))
    expect(new Set(fills).size).toBeGreaterThan(1)
  })

  it('gives nodes in the same community the same colour', () => {
    const { container } = draw()
    const circles = [...container.querySelectorAll('circle')]
    // a1, a2 are community 0; b1, b2 are community 1 (node order preserved).
    expect(circles[0].getAttribute('fill')).toBe(circles[1].getAttribute('fill'))
    expect(circles[2].getAttribute('fill')).toBe(circles[3].getAttribute('fill'))
  })

  it('says how many communities were found', () => {
    draw()
    expect(screen.getByText(/2 communities/i)).toBeInTheDocument()
  })

  it('falls back to the accent colour when the shaper sends no community', () => {
    // Older saved widgets and any future shaper that omits the field must keep
    // rendering rather than colouring by `undefined`.
    const { container } = draw({
      nodes: [{ id: 'x', x: 0.5, y: 0.5, degree: 1, closeness: 1, betweenness: 0, reach: 1 }],
      links: [],
    })
    expect(container.querySelector('circle')?.getAttribute('fill')).toBe('var(--accent)')
  })
})

describe('predicted links stay separate from observed ones', () => {
  it('does not draw suggestions until asked', () => {
    // Off by default: the chart's job is to show what happened. An inference
    // has to be opted into.
    const { container } = draw()
    expect(container.querySelectorAll('line')).toHaveLength(DATA.links.length)
  })

  it('draws them dashed once enabled, never as ordinary links', () => {
    // THE assertion. A solid line for an inferred relationship is the chart
    // claiming something the data does not say.
    const { container } = draw()
    fireEvent.click(screen.getByRole('checkbox'))

    const lines = [...container.querySelectorAll('line')]
    expect(lines).toHaveLength(DATA.links.length + DATA.suggested_links.length)
    const dashed = lines.filter(l => l.getAttribute('stroke-dasharray'))
    expect(dashed).toHaveLength(DATA.suggested_links.length)
    // And the real edges must not have picked up the dashed treatment.
    expect(lines.length - dashed.length).toBe(DATA.links.length)
  })

  it('offers the toggle only when there is something to suggest', () => {
    draw({ nodes: DATA.nodes, links: DATA.links, communities: 2 })
    expect(screen.queryByRole('checkbox')).toBeNull()
  })

  it('names how many suggestions there are', () => {
    draw()
    expect(screen.getByText(/suggested links \(1\)/i)).toBeInTheDocument()
  })
})
