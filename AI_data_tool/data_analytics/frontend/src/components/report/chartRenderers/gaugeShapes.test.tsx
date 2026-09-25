import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import GaugeRenderer from './GaugeRenderer'
import type { ChartRendererProps } from './types'

// Locale-agnostic: this machine's locale renders Arabic-Indic digits, so the
// expectation is computed with the same API fmtStr uses.
const V75 = (75).toLocaleString(undefined, { maximumFractionDigits: 2 })

const base: Omit<ChartRendererProps, 'cfg'> = {
  rows: [], data: { value: 75, target: 100 }, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: () => {}, ruleStyles: undefined,
}

describe('gauge shapes', () => {
  it('defaults to the arc (radial) shape', () => {
    const { container } = render(<GaugeRenderer {...base} cfg={{}} />)
    expect(screen.queryByTestId('gauge-bullet')).toBeNull()
    expect(screen.queryByTestId('gauge-speedometer')).toBeNull()
    expect(container.textContent).toContain(V75)
  })

  it('bullet: bar plus a target tick positioned by the target ratio', () => {
    render(<GaugeRenderer {...base} cfg={{ gauge_shape: 'bullet' }} />)
    expect(screen.getByTestId('gauge-bullet')).toBeInTheDocument()
    const tick = screen.getByTestId('gauge-bullet-target')
    // max = max(target, value) * 1.1 = 110; target 100 -> ~90.9%
    expect(tick.style.left).toMatch(/^90\.9/)
  })

  it('thermometer renders the tube and the value', () => {
    render(<GaugeRenderer {...base} cfg={{ gauge_shape: 'thermometer' }} />)
    const el = screen.getByTestId('gauge-thermometer')
    expect(el.querySelector('svg')).not.toBeNull()
    expect(el.textContent).toContain(V75)
  })

  it('progress shows the percentage of the scale', () => {
    render(<GaugeRenderer {...base} cfg={{ gauge_shape: 'progress' }} />)
    const el = screen.getByTestId('gauge-progress')
    // 75 / 110 = 68%
    expect(el.textContent).toContain('68%')
  })

  it('speedometer renders a needle', () => {
    render(<GaugeRenderer {...base} cfg={{ gauge_shape: 'speedometer' }} />)
    expect(screen.getByTestId('gauge-needle')).toBeInTheDocument()
  })

  it('a display-rule fill overrides attainment colour in every shape', () => {
    for (const shape of ['bullet', 'progress', 'thermometer'] as const) {
      const { unmount } = render(
        <GaugeRenderer {...base} cfg={{ gauge_shape: shape }}
          ruleStyles={{ rows: { 0: { fill: 'rgb(9, 9, 9)' } }, cells: {}, widget: {} } as any} />
      )
      const host = screen.getByTestId(`gauge-${shape}`)
      const painted = host.innerHTML.includes('rgb(9, 9, 9)')
      expect(painted, `${shape} should honour the rule fill`).toBe(true)
      unmount()
    }
  })
})

// Animation value options live in the same "one result, presentation options"
// family as the gauge shapes, so their tests share this file.
import BubbleChangePlotRenderer from './BubbleChangePlotRenderer'

describe('bubble-change animation value options', () => {
  const data = {
    frames: ['2024', '2025'],
    rows: [
      { name: 'A', x: 1, y: 2, size: 3, frame: '2024' },
      { name: 'A', x: 2, y: 3, size: 4, frame: '2025' },
    ],
  }
  const props = {
    rows: [], data, rtl: false, broadcasts: false,
    localSelected: null, onClickPoint: () => {},
  }

  it('hides the on-chart value by default (control bar only, as before)', () => {
    const { queryByTestId } = render(<BubbleChangePlotRenderer {...props} cfg={{}} />)
    expect(queryByTestId('anim-value-label')).toBeNull()
  })

  it('places, sizes and styles the value per config, with a contrast box', () => {
    const { getByTestId } = render(
      <BubbleChangePlotRenderer {...props} cfg={{
        anim_label_position: 'top-right', anim_label_size: 60,
        anim_label_style: 'italic', anim_label_opacity: 0.5, anim_label_box: true,
      }} />
    )
    const el = getByTestId('anim-value-label')
    expect(el.textContent).toBe('2024')
    expect(el.style.fontSize).toBe('60px')
    expect(el.style.fontStyle).toBe('italic')
    expect(el.style.top).toBe('8px')
    expect(el.style.right).toBe('12px')
    expect(el.style.border).toContain('1px solid')
  })

  it('descending order starts from the last frame', () => {
    const { getByTestId } = render(
      <BubbleChangePlotRenderer {...props} cfg={{ anim_label_position: 'center', anim_order: 'desc' }} />
    )
    expect(getByTestId('anim-value-label').textContent).toBe('2025')
  })
})
