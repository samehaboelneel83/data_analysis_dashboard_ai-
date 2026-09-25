import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ForecastChartRenderer from './ForecastChartRenderer'
import type { ChartRendererProps } from './types'

/**
 * "When will this reach X?" on the forecast itself.
 *
 * Goal-seek existed, solving across two columns on a linear fit. A forecast
 * existed, projecting a series forward with a band. Neither knew about the
 * other, so the question a forecast most obviously invites had no answer.
 *
 * The answer is computed by the SHAPER, not here — `shape_forecast` already has
 * the history and the projection in hand, and a caption computed separately
 * could disagree with the chart it sits under. This renderer's job is to say it
 * plainly and to mark the period on the axis.
 */

const base: Omit<ChartRendererProps, 'data'> = {
  rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null,
  onClickPoint: () => {},
} as never

const payload = (goal: Record<string, unknown> | undefined) => ({
  type: 'forecast',
  rows: [{ name: '2025-11', value: 95 }, { name: '2025-12', value: 98 }],
  forecast: [
    { name: '2026-01', yhat: 100, lo: 80, hi: 115 },
    { name: '2026-02', yhat: 110, lo: 85, hi: 135 },
    { name: '2026-03', yhat: 120, lo: 88, hi: 152 },
  ],
  ...(goal ? { goal } : {}),
})

const draw = (goal?: Record<string, unknown>) =>
  render(<ForecastChartRenderer {...base} data={payload(goal) as never} />)

describe('a forecast with no target', () => {
  it('says nothing extra', () => {
    // The overwhelmingly common case. A forecast that has never been given a
    // target must look exactly as it always did.
    const { container } = draw()
    expect(container.querySelector('[data-testid="forecast-goal"]')).toBeNull()
  })
})

describe('a target the projection reaches', () => {
  const reached = {
    target: 120, direction: 'rise', last_actual: 98,
    reached_in_history: null, expected_period: '2026-03',
    earliest_period: '2026-02', latest_period: null,
    within_horizon: true, horizon: 3,
    end_period: '2026-03', end_value: 120, end_lo: 88, end_hi: 152,
  }

  it('names the period', () => {
    draw(reached)
    expect(screen.getByTestId('forecast-goal')).toHaveTextContent('2026-03')
  })

  it('gives the range the band allows, not just the point estimate', () => {
    // A single date from a projection whose interval spans 64 units would be
    // false precision. The band is the honest part of a forecast.
    draw(reached)
    expect(screen.getByTestId('forecast-goal')).toHaveTextContent(/2026-02/)
  })

  it('says the target it is answering', () => {
    // Through `toLocaleString`, so the expectation goes through it too: under
    // an Arabic locale this renders ١٢٠, correct for a reader there and a false
    // failure for a hardcoded "120".
    draw(reached)
    expect(screen.getByTestId('forecast-goal'))
      .toHaveTextContent((120).toLocaleString())
  })
})

describe('a target already met', () => {
  const already = {
    target: 400, direction: 'rise', last_actual: 385,
    reached_in_history: { period: '2025-05', value: 422 },
    expected_period: null, earliest_period: null, latest_period: null,
    within_horizon: false, horizon: 3,
    end_period: '2026-03', end_value: 381, end_lo: 307, end_hi: 454,
  }

  it('says when it happened rather than "not within the horizon"', () => {
    // The answer a horizon-only reading gets exactly wrong, and the case the
    // demo data is full of.
    draw(already)
    const caption = screen.getByTestId('forecast-goal')
    expect(caption).toHaveTextContent(/2025-05/)
    expect(caption).toHaveTextContent(/reached/i)
  })

  it('still warns that the projection does not get back there', () => {
    draw(already)
    expect(screen.getByTestId('forecast-goal')).toHaveTextContent(/not expected/i)
  })
})

describe('a target the projection never reaches', () => {
  const short = {
    target: 900, direction: 'rise', last_actual: 98,
    reached_in_history: null, expected_period: null,
    earliest_period: null, latest_period: null,
    within_horizon: false, horizon: 3,
    end_period: '2026-03', end_value: 120, end_lo: 88, end_hi: 152,
  }

  it('says how far short it ends up', () => {
    // "Not within 3 periods" alone leaves the reader guessing whether they
    // missed by a little or by a factor of seven.
    draw(short)
    const caption = screen.getByTestId('forecast-goal')
    expect(caption).toHaveTextContent((120).toLocaleString())
    expect(caption).toHaveTextContent(/2026-03/)
  })

  it('does not claim a date it does not have', () => {
    draw(short)
    expect(screen.getByTestId('forecast-goal')).not.toHaveTextContent(/expected 2026/i)
  })
})

describe('possible but not expected', () => {
  it('distinguishes the band crossing from the estimate crossing', () => {
    // "The optimistic edge gets there in March, the central estimate does not"
    // is a different answer from "no", and a more useful one.
    draw({
      target: 150, direction: 'rise', last_actual: 98,
      reached_in_history: null, expected_period: null,
      earliest_period: '2026-03', latest_period: null,
      within_horizon: false, horizon: 3,
      end_period: '2026-03', end_value: 120, end_lo: 88, end_hi: 152,
    })
    const caption = screen.getByTestId('forecast-goal')
    expect(caption).toHaveTextContent(/2026-03/)
    expect(caption).toHaveTextContent(/possible|optimistic|best case/i)
  })
})

describe('already reached, and the band allows a return', () => {
  /**
   * The live demo case, and one the first caption got half right.
   *
   * Revenue passed 400k in 2025-01 and the projection has since settled near
   * 381k, so the central estimate does not return — but the optimistic edge of
   * the interval clears 400k from the very first forecast period. Saying only
   * "not expected to return" drops exactly the information the band exists to
   * carry, in a component whose whole argument is that the band is the honest
   * part of a forecast.
   */
  const both = {
    target: 400000, direction: 'rise', last_actual: 352211,
    reached_in_history: { period: '2025-01', value: 433051 },
    expected_period: null, earliest_period: '2026-01', latest_period: null,
    within_horizon: false, horizon: 6,
    end_period: '2026-06', end_value: 380863, end_lo: 307000, end_hi: 453000,
  }

  it('still leads with when it happened', () => {
    draw(both)
    expect(screen.getByTestId('forecast-goal')).toHaveTextContent(/2025-01/)
  })

  it('does not hide that a return is possible', () => {
    draw(both)
    const caption = screen.getByTestId('forecast-goal')
    expect(caption).toHaveTextContent(/2026-01/)
    expect(caption).toHaveTextContent(/possible|optimistic|best case/i)
  })

  it('says plainly that it is not the expectation', () => {
    draw(both)
    expect(screen.getByTestId('forecast-goal')).toHaveTextContent(/not expected/i)
  })
})
