/**
 * E10: chart marks recharts draws as role="img" without a name are hidden
 * from assistive technology (axe svg-img-alt found 150 on one scatter); a
 * mark that carries a name, like a pie slice, is left for screen readers.
 */
import { describe, it, expect } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import { MeasuredChart } from './MeasuredChart'

function Marks({ extra = 0 }: { extra?: number }) {
  return (
    <svg>
      <g role="img" data-testid="unnamed" />
      <path role="img" aria-label="North: 150" data-testid="named" />
      {Array.from({ length: extra }, (_, i) => <g key={i} role="img" data-testid={`later-${i}`} />)}
    </svg>
  )
}

function Redraws() {
  const [n, setN] = useState(0)
  useEffect(() => { const t = setTimeout(() => setN(2), 10); return () => clearTimeout(t) }, [])
  return <Marks extra={n} />
}

describe('MeasuredChart', () => {
  it('hides unnamed marks and keeps named ones', () => {
    const { getByTestId } = render(<MeasuredChart>{() => <Marks />}</MeasuredChart>)
    expect(getByTestId('unnamed')).toHaveAttribute('aria-hidden', 'true')
    expect(getByTestId('named')).not.toHaveAttribute('aria-hidden')
  })

  it('hides marks drawn after the first render too', async () => {
    const { getByTestId } = render(<MeasuredChart>{() => <Redraws />}</MeasuredChart>)
    await waitFor(() => expect(getByTestId('later-1')).toHaveAttribute('aria-hidden', 'true'))
  })
})
