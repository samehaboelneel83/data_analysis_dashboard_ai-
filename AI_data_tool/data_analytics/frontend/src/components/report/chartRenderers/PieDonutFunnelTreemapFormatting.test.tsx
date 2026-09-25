import { describe, it, expect, beforeAll } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import PieChartRenderer from './PieChartRenderer'
import DonutChartRenderer from './DonutChartRenderer'
import FunnelChartRenderer from './FunnelChartRenderer'
import TreemapChartRenderer from './TreemapChartRenderer'

// Slice 1 of the widget-enhancement roadmap: pie/donut/funnel/treemap silently
// ignored FormatConfig entirely (widgetCapabilities.ts documented this as a
// pre-existing gap). These prove each renderer now actually reads the config
// it is given, and — just as important — that an UNSET config still renders
// exactly as it always did, so no existing dashboard changes underneath its
// author.
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: 400, height: 300, top: 0, left: 0, right: 400, bottom: 300, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const rows = [
  { name: 'North America', value: 40 },
  { name: 'Europe', value: 30 },
  { name: 'Asia Pacific', value: 20 },
]

const wrap = (ui: React.ReactElement) => render(<div style={{ width: 400, height: 300 }}>{ui}</div>)

const percentLabels = (container: HTMLElement) =>
  [...container.querySelectorAll('text')].filter(t => (t.textContent ?? '').includes('%'))

describe('PieChartRenderer data labels', () => {
  it('shows the percent-of-total label by default (historical always-on look)', async () => {
    const { container } = wrap(
      <PieChartRenderer rows={rows} data={{}} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    // Pie's label text does not paint until its (real-timer-driven) sector
    // animation finishes, well past testing-library's default 1000ms budget --
    // same cause as NumericSeriesPlotRenderer's dots, see ruleFillWiring.test.tsx.
    await waitFor(() => expect(percentLabels(container).length).toBeGreaterThan(0), { timeout: 2000 })
  })

  it('hides the label when cfg.data_labels is explicitly false', async () => {
    const { container } = wrap(
      <PieChartRenderer rows={rows} data={{}} cfg={{ data_labels: false }} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    // Give the chart the same settle time as the "shown" case above before
    // asserting the negative, so this isn't just catching a slow first paint.
    await waitFor(() => expect(container.querySelectorAll('.recharts-pie-sector').length).toBeGreaterThan(0))
    expect(percentLabels(container).length).toBe(0)
  })
})

describe('DonutChartRenderer legend and data labels', () => {
  it('shows the legend by default (historical always-on look)', () => {
    const { container } = wrap(
      <DonutChartRenderer rows={rows} data={{}} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(container.querySelectorAll('.recharts-legend-wrapper').length).toBe(1)
  })

  it('hides the legend when cfg.legend is explicitly false', () => {
    const { container } = wrap(
      <DonutChartRenderer rows={rows} data={{}} cfg={{ legend: false }} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(container.querySelectorAll('.recharts-legend-wrapper').length).toBe(0)
  })

  it('shows no percent-of-total label by default (historical never-shown look)', () => {
    const { container } = wrap(
      <DonutChartRenderer rows={rows} data={{}} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(percentLabels(container).length).toBe(0)
  })

  it('shows the percent-of-total label when cfg.data_labels is explicitly true', async () => {
    const { container } = wrap(
      <DonutChartRenderer rows={rows} data={{}} cfg={{ data_labels: true }} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    await waitFor(() => expect(percentLabels(container).length).toBeGreaterThan(0))
  })
})

describe('FunnelChartRenderer data labels and patterns', () => {
  const funnelRows = [{ name: 'Visited', value: 100 }, { name: 'Bought', value: 40 }]

  it('shows the name label by default (historical always-on look)', () => {
    const { container } = wrap(
      <FunnelChartRenderer rows={funnelRows} data={{}} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(container.querySelectorAll('.recharts-label-list text').length).toBeGreaterThan(0)
  })

  it('hides the name label when cfg.data_labels is explicitly false', () => {
    const { container } = wrap(
      <FunnelChartRenderer rows={funnelRows} data={{}} cfg={{ data_labels: false }} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(container.querySelectorAll('.recharts-label-list text').length).toBe(0)
  })

  it('hatches its segments when cfg.series_patterns is set, like pie/donut', () => {
    const { container } = wrap(
      <FunnelChartRenderer rows={funnelRows} data={{}} cfg={{ series_patterns: true }} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(container.querySelectorAll('pattern[id^="fillpat-"]').length).toBeGreaterThan(0)
  })
})

describe('TreemapChartRenderer data labels and tooltip', () => {
  const tmRows = [{ name: 'Big Node', value: 100 }, { name: 'Small', value: 1 }]

  const nodeNameTexts = (container: HTMLElement) =>
    [...container.querySelectorAll('text')].filter(t => t.textContent === 'Big Node')

  it('shows the node-name text by default (historical always-on look)', () => {
    const { container } = wrap(
      <TreemapChartRenderer rows={tmRows} data={{}} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(nodeNameTexts(container).length).toBeGreaterThan(0)
  })

  it('hides the node-name text when cfg.data_labels is explicitly false', () => {
    const { container } = wrap(
      <TreemapChartRenderer rows={tmRows} data={{}} cfg={{ data_labels: false }} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} />
    )
    expect(nodeNameTexts(container).length).toBe(0)
  })

  it('mounts a tooltip wrapper so a hovered node can show its formatted value', () => {
    const { container } = wrap(
      <TreemapChartRenderer rows={tmRows} data={{}} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}} measureFmt={undefined} />
    )
    expect(container.querySelectorAll('.recharts-tooltip-wrapper').length).toBe(1)
  })
})
