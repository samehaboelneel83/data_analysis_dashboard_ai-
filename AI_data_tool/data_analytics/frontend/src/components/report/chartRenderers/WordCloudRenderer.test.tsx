import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

/** C-06: the word cloud drew nothing for long product names sized by revenue.
 *  d3-cloud is mocked to record what the renderer asks of it and to answer
 *  with a chosen set of placed words. */
const calls: { size?: [number, number]; fontSize?: (d: any) => number; words?: any[] }[] = []
let placeAll = true
vi.mock('d3-cloud', () => ({
  default: () => {
    const rec: (typeof calls)[number] = {}
    calls.push(rec)
    let end: (w: any[]) => void = () => {}
    const api: any = {
      size: (s: [number, number]) => { rec.size = s; return api },
      words: (w: any[]) => { rec.words = w; return api },
      padding: () => api, rotate: () => api, font: () => api,
      fontSize: (f: (d: any) => number) => { rec.fontSize = f; return api },
      on: (_: string, cb: (w: any[]) => void) => { end = cb; return api },
      start: () => { end(placeAll ? (rec.words ?? []).map(w => ({ ...w, size: rec.fontSize!(w), x: 0, y: 0, rotate: 0 })) : []) },
    }
    return api
  },
}))

import WordCloudRenderer from './WordCloudRenderer'

const longNames = Array.from({ length: 10 }, (_, i) => ({
  name: `Aurora Enterprise Suite ${i}`.padEnd(25, 'x'), value: 60000 + i * 1500 }))

const base = { data: {}, cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {} } as any

beforeEach(() => { calls.length = 0; placeAll = true })

describe('WordCloudRenderer (C-06)', () => {
  it('lays out in the tile\'s plot box and sizes the longest word to fit its width', () => {
    render(<WordCloudRenderer {...base} rows={longNames} plotW={420} plotH={260} />)
    const c = calls[calls.length - 1]
    expect(c.size).toEqual([420, 260])
    const biggest = Math.max(...longNames.map(w => c.fontSize!({ text: w.name, value: w.value })))
    // ~0.6 em per character: a 25-character word at this size fits 420 px.
    expect(biggest * 25 * 0.6).toBeLessThanOrEqual(420)
  })

  it('spreads sizes between the smallest and largest value (not from 0)', () => {
    render(<WordCloudRenderer {...base} rows={longNames} plotW={800} plotH={400} />)
    const c = calls[calls.length - 1]
    const sizes = longNames.map(w => c.fontSize!({ text: w.name, value: w.value }))
    expect(Math.max(...sizes) - Math.min(...sizes)).toBeGreaterThan(10)
  })

  it('says so when no word fits, instead of a blank tile', () => {
    placeAll = false
    render(<WordCloudRenderer {...base} rows={longNames} plotW={300} plotH={200} />)
    expect(calls.length).toBeGreaterThanOrEqual(2)          // retried smaller once
    expect(screen.getByText(/too long to fit/i)).toBeInTheDocument()
  })
})
