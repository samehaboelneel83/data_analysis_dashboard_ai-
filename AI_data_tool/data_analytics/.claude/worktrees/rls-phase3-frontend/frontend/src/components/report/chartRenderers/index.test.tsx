import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CHART_RENDERERS } from './index'
import type { ChartRendererProps } from './types'

describe('CHART_RENDERERS registry', () => {
  it('has bar chart registered', () => {
    expect(Object.keys(CHART_RENDERERS)).toContain('bar')
  })

  it('renders whatever component is registered for a widget type', () => {
    const TestRenderer: React.FC<ChartRendererProps> = ({ rows }) => (
      <div data-testid="test-chart">{rows.length} rows</div>
    )
    CHART_RENDERERS['bar'] = TestRenderer
    const Registered = CHART_RENDERERS['bar']!
    render(<Registered rows={[{ name: 'a', value: 1 }]} data={{}} cfg={{}} rtl={false} broadcasts={false}
      localSelected={null} onClickPoint={() => {}} />)
    expect(screen.getByTestId('test-chart')).toHaveTextContent('1 rows')
    delete CHART_RENDERERS['bar']
  })
})
