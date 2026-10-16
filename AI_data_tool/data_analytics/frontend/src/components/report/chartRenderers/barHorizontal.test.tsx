import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import BarChartRenderer from './BarChartRenderer'

// Recharts measures its container; give it a size so it draws in jsdom.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    <actual.ResponsiveContainer width={420} height={260}>{children}</actual.ResponsiveContainer> }
})

const rows = [{ name: 'A long category name', value: 30 }, { name: 'Second', value: 20 }, { name: 'Third', value: 10 }]
const draw = (cfg: Record<string, unknown>) => render(
  <div style={{ width: 420, height: 260 }}>
    <BarChartRenderer rows={rows} data={{ type: 'series', rows }} cfg={{ dimension: 'k', measure: 'v', ...cfg } as never}
      rtl={false} broadcasts={false} localSelected={null} onClickPoint={() => {}} plotW={420} plotH={260} />
  </div>)

describe('bars lying down', () => {
  it('draws each category on its own line, read whole, when asked to', () => {
    const { container } = draw({ orientation: 'horizontal' })
    const chart = container.querySelector('.recharts-wrapper')
    expect(chart).toBeTruthy()
    // The category axis is the vertical one: its labels are the names, untilted.
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')].map(n => n.textContent)
    expect(yTicks).toEqual(['A long category name', 'Second', 'Third'])
  })

  it('stays upright without the setting', () => {
    const { container } = draw({})
    const xTicks = [...container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].map(n => n.textContent).join(' ')
    expect(xTicks).toContain('Second')
  })
})

describe('bars lying down, many of them (F-14 step 3)', () => {
  it('draws every category: the width-based window for upright labels does not apply', () => {
    const many = ['Egypt', 'Saudi Arabia', 'United Arab Emirates', 'Kuwait', 'Qatar', 'Bahrain', 'Oman', 'Jordan',
      'Lebanon', 'Morocco', 'Tunisia', 'Algeria', 'Iraq', 'Libya'].map((name, i) => ({ name, value: 100 - i }))
    const onBrushChange = vi.fn()
    const { container } = render(
      <div style={{ width: 420, height: 260 }}>
        <BarChartRenderer rows={many} data={{ type: 'series', rows: many }}
          cfg={{ dimension: 'country', aggregation: 'count', orientation: 'horizontal' } as never}
          rtl={false} broadcasts={false} localSelected={null} onClickPoint={() => {}} plotW={300} plotH={260}
          onBrushChange={onBrushChange} />
      </div>)
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')].map(n => n.textContent)
    expect(yTicks).toHaveLength(14)
    // ...and the tile does not claim a slice is shown.
    expect(onBrushChange.mock.calls.every(([r]) => r === null)).toBe(true)
  })
})
