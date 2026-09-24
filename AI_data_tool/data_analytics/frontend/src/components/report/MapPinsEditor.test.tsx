/**
 * Authoring map pins.
 *
 * The renderer silently drops a pin whose coordinates it cannot use — it has to,
 * because a NaN coordinate throws inside d3 and takes the whole map down. That
 * makes the editor the only place the author can be told, and an editor that
 * accepts "48,85" or a blank latitude without comment reproduces this codebase's
 * favourite failure: it works for the author who typed a good one, and the pin
 * that quietly never appears is someone else's problem.
 *
 * So the interesting assertions here are about the pins that WON'T draw.
 */
import { useState } from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import MapPinsEditor from './MapPinsEditor'
import type { MapPin } from './MapPinsEditor'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import type { Widget } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

const pin = (over: object = {}) => ({ label: 'Depot', lat: '48.85', lon: '2.35', ...over })

describe('MapPinsEditor', () => {
  it('says so when there are no pins yet', () => {
    render(<MapPinsEditor value={[]} onChange={vi.fn()} />)
    expect(screen.getByText(/no pins/i)).toBeInTheDocument()
  })

  it('shows a row per pin', () => {
    render(<MapPinsEditor value={[pin(), pin({ label: 'Flood line', lat: '51.5', lon: '-0.12' })]}
      onChange={vi.fn()} />)
    expect(screen.getByDisplayValue('Depot')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Flood line')).toBeInTheDocument()
  })

  it('adds a pin', () => {
    const onChange = vi.fn()
    render(<MapPinsEditor value={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /add pin/i }))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ label: expect.any(String) })])
  })

  it('edits a label', () => {
    const onChange = vi.fn()
    render(<MapPinsEditor value={[pin()]} onChange={onChange} />)
    fireEvent.change(screen.getByDisplayValue('Depot'), { target: { value: 'New depot' } })
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ label: 'New depot' })])
  })

  it('passes the typed coordinate through untouched', () => {
    // The editor deals in what the author is holding. Parsing here is what ate
    // the decimal point; the number is produced once, at save, and the seam
    // test below is what proves it.
    const onChange = vi.fn()
    render(<MapPinsEditor value={[pin()]} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText(/latitude for depot/i), { target: { value: '51.5' } })
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ lat: '51.5' })])
  })

  it('removes a pin', () => {
    const onChange = vi.fn()
    render(<MapPinsEditor value={[pin(), pin({ label: 'Second' })]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /remove pin depot/i }))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ label: 'Second' })])
  })

  it('warns that an incomplete pin will not be drawn', () => {
    render(<MapPinsEditor value={[pin({ lat: '' })]} onChange={vi.fn()} />)
    expect(screen.getByText(/won't be drawn|will not be drawn/i)).toBeInTheDocument()
  })

  it('warns about a latitude outside its range', () => {
    // 95°N does not exist. d3 still projects it, to somewhere meaningless, so
    // nothing downstream complains — the author just sees a pin in the wrong
    // place and doubts the map.
    render(<MapPinsEditor value={[pin({ lat: '95' })]} onChange={vi.fn()} />)
    expect(screen.getByText(/-90 and 90/)).toBeInTheDocument()
  })

  it('warns about a longitude outside its range', () => {
    render(<MapPinsEditor value={[pin({ lon: '200' })]} onChange={vi.fn()} />)
    expect(screen.getByText(/-180 and 180/)).toBeInTheDocument()
  })

  it('lets a decimal point survive being typed', () => {
    // A controlled input bound to a PARSED NUMBER eats the keystroke: "48."
    // parses to 48, re-renders as "48", and the dot the author just pressed is
    // gone. They cannot reach 48.85 at all. fireEvent.change with a whole
    // string hides this completely, which is why the assertion is on the
    // intermediate state.
    const Harness = () => {
      const [pins, setPins] = useState<MapPin[]>([pin({ lat: '' })])
      return <MapPinsEditor value={pins} onChange={setPins} />
    }
    render(<Harness />)
    const lat = screen.getByLabelText(/latitude for depot/i)
    fireEvent.change(lat, { target: { value: '48.' } })
    expect(lat).toHaveValue('48.')
  })

  it('lets a minus sign survive being typed', () => {
    // Every southern latitude and western longitude starts with one.
    const Harness = () => {
      const [pins, setPins] = useState<MapPin[]>([pin({ lat: '' })])
      return <MapPinsEditor value={pins} onChange={setPins} />
    }
    render(<Harness />)
    const lat = screen.getByLabelText(/latitude for depot/i)
    fireEvent.change(lat, { target: { value: '-' } })
    expect(lat).toHaveValue('-')
  })

  it('says nothing about a pin that is fine', () => {
    render(<MapPinsEditor value={[pin()]} onChange={vi.fn()} />)
    expect(screen.queryByText(/won't be drawn|will not be drawn/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/-90 and 90/)).not.toBeInTheDocument()
  })
})

/**
 * The seam. The editor emits pins and the panel writes config, and each can be
 * right while nothing reaches the widget — the failure this codebase has hit
 * often enough to have a name for it.
 */
describe('pins reach the widget config', () => {
  const COLUMNS: DatasetColumn[] = [
    { id: 0, name: 'lat', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 1, name: 'lon', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 2, name: 'site', dtype: 'text', missing_pct: 0, stats: {} },
  ] as DatasetColumn[]

  function panel(widgetType: string, config: Record<string, unknown> = {}) {
    const onUpdate = vi.fn()
    const widget: Widget = {
      id: 1, page_id: 100, widget_type: widgetType as Widget['widget_type'],
      title: '', config, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }
    render(
      <CrossFilterProvider>
        <WidgetConfigPanel widget={widget} columns={COLUMNS} onUpdate={onUpdate} />
      </CrossFilterProvider>,
    )
    return onUpdate
  }

  /** The save is debounced and skips the first render, so the timers have to be
   *  advanced inside act() before anything is asserted. */
  const lastConfig = (onUpdate: ReturnType<typeof vi.fn>) => {
    act(() => { vi.advanceTimersByTime(1000) })
    const calls = onUpdate.mock.calls
    expect(calls.length).toBeGreaterThan(0)
    const arg = calls[calls.length - 1][0]
    return (arg?.config ?? arg) as Record<string, unknown>
  }

  beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers(); localStorage.clear() })
  afterEach(() => vi.useRealTimers())

  it('offers the editor on a point map and saves what was typed', () => {
    const onUpdate = panel('map_points')
    fireEvent.click(screen.getByRole('button', { name: /add pin/i }))
    fireEvent.change(screen.getByLabelText(/^label for pin 1$/i), { target: { value: 'Depot' } })
    fireEvent.change(screen.getByLabelText(/^latitude for depot$/i), { target: { value: '48.85' } })
    fireEvent.change(screen.getByLabelText(/^longitude for depot$/i), { target: { value: '2.35' } })

    expect(lastConfig(onUpdate).pins)
      .toEqual([{ label: 'Depot', lat: 48.85, lon: 2.35 }])
  })

  it('restores pins already on the widget', () => {
    panel('map_points', { pins: [{ label: 'Existing', lat: 1, lon: 2 }] })
    expect(screen.getByDisplayValue('Existing')).toBeInTheDocument()
  })

  it('does not offer pins on a choropleth', () => {
    // Shapes, not coordinates: there is nothing on screen for a lat/lon to
    // anchor to at that scale.
    panel('map_choropleth')
    expect(screen.queryByRole('button', { name: /add pin/i })).not.toBeInTheDocument()
  })
})
