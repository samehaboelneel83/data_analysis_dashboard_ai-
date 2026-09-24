import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import MiniBarChart from './MiniBarChart'

describe('MiniBarChart', () => {
  it('renders a horizontal bar per row, labelled and sorted by value descending', () => {
    render(<MiniBarChart rows={[
      { name: 'EMEA', value: 10 },
      { name: 'APAC', value: 40 },
      { name: 'AMER', value: 25 },
    ]} />)

    const bars = screen.getAllByTestId('mini-bar-row')
    expect(bars.map(b => b.textContent)).toEqual([
      expect.stringContaining('APAC'),
      expect.stringContaining('AMER'),
      expect.stringContaining('EMEA'),
    ])
  })

  it('caps the display to the top 5 rows by value', () => {
    render(<MiniBarChart rows={Array.from({ length: 8 }, (_, i) => ({ name: `c${i}`, value: i }))} />)
    expect(screen.getAllByTestId('mini-bar-row')).toHaveLength(5)
  })

  it('keeps histogram bins in range order, never sorted by count', () => {
    // THE bug: a histogram came out "16.00–265.20, 265.20–514.40, 4750.80–500…,
    // 514.40–763.60" -- its bins in frequency order. Sorting a distribution by
    // count destroys the only thing the chart exists to show.
    render(<MiniBarChart ordered rows={[
      { name: '0–10', value: 17, bin_start: 0, bin_end: 10 },
      { name: '10–20', value: 15, bin_start: 10, bin_end: 20 },
      { name: '20–30', value: 1, bin_start: 20, bin_end: 30 },
      { name: '30–40', value: 22, bin_start: 30, bin_end: 40 },
    ]} />)

    // The label is the row's first span; textContent would run it into the
    // count beside it ("0–10" + "17" = "0–1017").
    const labels = screen.getAllByTestId('mini-bar-row')
      .map(b => b.firstElementChild!.textContent)
    expect(labels).toEqual(['0–10', '10–20', '20–30', '30–40'])
  })

  it('still ranks a categorical bar by value, which is what that chart means', () => {
    render(<MiniBarChart rows={[
      { name: 'a', value: 1 }, { name: 'b', value: 9 }, { name: 'c', value: 5 },
    ]} />)
    expect(screen.getAllByTestId('mini-bar-row').map(b => b.textContent))
      .toEqual([
        expect.stringContaining('b'),
        expect.stringContaining('c'),
        expect.stringContaining('a'),
      ])
  })

  const bin = (name: string, value: number, lo: number, hi: number) =>
    ({ name, value, bin_start: lo, bin_end: hi })
  const labels = () => screen.getAllByTestId('mini-bar-row')
    .map(b => b.firstElementChild!.textContent)

  it('drops empty bins at the ends, which are only padding', () => {
    render(<MiniBarChart ordered rows={[
      bin('0–10', 0, 0, 10),
      bin('10–20', 5, 10, 20),
      bin('20–30', 3, 20, 30),
      bin('30–40', 0, 30, 40),
      bin('40–50', 0, 40, 50),
    ]} />)
    expect(labels()).toEqual(['10–20', '20–30'])
  })

  it('KEEPS an empty bin in the middle, which is real distributional information', () => {
    // A hole between two populated bins is a fact about the data -- often the
    // most interesting one on the chart. Closing it would draw a distribution
    // the dataset does not have.
    render(<MiniBarChart ordered rows={[
      bin('0–10', 5, 0, 10),
      bin('10–20', 0, 10, 20),
      bin('20–30', 4, 20, 30),
    ]} />)
    expect(labels()).toEqual(['0–10', '10–20', '20–30'])
  })

  it('merges adjacent bins rather than cutting the tail off', () => {
    // Slicing to the first N would drop the far outlier, and on an
    // outlier_impact finding the outlier IS the finding.
    render(<MiniBarChart ordered rows={
      Array.from({ length: 24 }, (_, i) =>
        bin(`${i * 10}–${(i + 1) * 10}`, i === 23 ? 7 : 1, i * 10, (i + 1) * 10))
    } />)
    const shown = labels()
    expect(shown.length).toBeLessThanOrEqual(12)
    // First lower bound and last upper bound both survive the merge.
    expect(shown[0]!.startsWith('0–')).toBe(true)
    expect(shown[shown.length - 1]!.endsWith('–240')).toBe(true)
  })

  it('preserves the total count when it merges', () => {
    render(<MiniBarChart ordered rows={
      Array.from({ length: 24 }, (_, i) => bin(`${i}–${i + 1}`, 2, i, i + 1))
    } />)
    const counts = screen.getAllByTestId('mini-bar-row')
      .map(b => Number(b.lastElementChild!.textContent))
    expect(counts.reduce((a, b) => a + b, 0)).toBe(48)
  })

  it('shows both bounds of a large bin instead of truncating one away', () => {
    // THE bug: the server formats "4750.80–500000.00" and a 72px column cut it
    // to "4750.80–500…" -- hiding the half the reader wanted.
    render(<MiniBarChart ordered rows={[
      bin('4750.80–500000.00', 3, 4750.8, 500000),
      bin('500000.00–1012345.00', 1, 500000, 1012345),
    ]} />)
    expect(labels()).toEqual(['4.8k–500k', '500k–1M'])
  })

  it('does not round small bounds, where rounding would misstate the bin', () => {
    // "0.8–1.2" and "1–1" are not the same bin.
    render(<MiniBarChart ordered rows={[bin('0.80–1.20', 4, 0.8, 1.2)]} />)
    expect(labels()).toEqual(['0.8–1.2'])
  })

  it("keeps the server's exact label reachable on hover", () => {
    render(<MiniBarChart ordered rows={[bin('4750.80–500000.00', 3, 4750.8, 500000)]} />)
    expect(screen.getAllByTestId('mini-bar-row')[0].firstElementChild)
      .toHaveAttribute('title', '4750.80–500000.00')
  })

  it('leaves categorical labels exactly as the server sent them', () => {
    render(<MiniBarChart rows={[{ name: 'EMEA', value: 3 }]} />)
    expect(labels()).toEqual(['EMEA'])
  })

  it('renders nothing when every bin is empty', () => {
    const { container } = render(<MiniBarChart ordered rows={[
      bin('0–10', 0, 0, 10), bin('10–20', 0, 10, 20),
    ]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for an empty row set', () => {
    const { container } = render(<MiniBarChart rows={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
