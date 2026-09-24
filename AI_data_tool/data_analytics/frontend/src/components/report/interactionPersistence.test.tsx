import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'
import InteractionSettings from './InteractionSettings'
import type { Widget } from '../../types/report'

/**
 * Interactions have to survive a reload.
 *
 * The Interactions panel offers a real model — broadcast/receive direction, a
 * filter-or-highlight receive mode, per-pair actions, sync across pages — and
 * every one of those choices lived in React state and nowhere else. Nothing
 * read them back, nothing wrote them down. Set a widget to receive-only, press
 * F5, and it is broadcasting again with no indication anything was lost.
 *
 * They now live in `widget.config.interaction`, the JSON blob the widget
 * already owns, so persisting one is the PATCH the builder already makes.
 *
 * The trap this file exists to pin: `InteractionSettings` initialises a widget
 * to "broadcasts and receives" the first time its panel opens. If that effect
 * runs against a widget whose stored value has not been hydrated yet, it
 * overwrites it — and the user watches their setting revert as they open the
 * panel to look at it.
 */
function widget(id: number, interaction?: unknown): Widget {
  return {
    id, page_id: 1, widget_type: 'bar', title: `W${id}`,
    config: { dimension: 'department', measure: 'cost',
              ...(interaction ? { interaction } : {}) },
    layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '2026-01-01',
  } as Widget
}

/** Reads the live interaction map out of the context. */
function Probe({ id }: { id: number }) {
  const { interactions } = useCrossFilter()
  return <div data-testid={`probe-${id}`}>{JSON.stringify(interactions[id] ?? null)}</div>
}

function mount(widgets: Widget[], onPersist = vi.fn(), withPanel?: number) {
  render(
    <CrossFilterProvider widgets={widgets} onPersistInteraction={onPersist}>
      {widgets.map(w => <Probe key={w.id} id={w.id} />)}
      {withPanel !== undefined && (
        <InteractionSettings widget={widgets.find(w => w.id === withPanel)!}
                             pageWidgets={widgets} />
      )}
    </CrossFilterProvider>)
  return onPersist
}

const read = (id: number) =>
  JSON.parse(screen.getByTestId(`probe-${id}`).textContent || 'null')

describe('hydrating from what was saved', () => {
  it('restores a stored interaction', () => {
    mount([widget(1, { broadcasts: false, receives: true })])
    expect(read(1)).toMatchObject({ broadcasts: false, receives: true })
  })

  it('restores the receive mode', () => {
    mount([widget(1, { broadcasts: true, receives: true, receiveMode: 'highlight' })])
    expect(read(1).receiveMode).toBe('highlight')
  })

  it('restores per-pair actions', () => {
    mount([widget(1, { broadcasts: true, receives: true,
                       actions: [{ targetId: 2, mode: 'filter' }] }),
           widget(2)])
    expect(read(1).actions).toEqual([{ targetId: 2, mode: 'filter' }])
  })

  it('leaves a widget that never had one unset', () => {
    mount([widget(1)])
    expect(read(1)).toBeNull()
  })

  it('ignores a stored value that is not an object', () => {
    mount([widget(1, 'nonsense')])
    expect(read(1)).toBeNull()
  })
})

describe('opening the settings panel does not stomp what was saved', () => {
  it('keeps receives:false when the panel initialises', async () => {
    // THE race. The panel's "default it on first open" effect must not fire
    // for a widget that already has a value.
    mount([widget(1, { broadcasts: true, receives: false })], vi.fn(), 1)
    await waitFor(() => expect(read(1)).not.toBeNull())
    expect(read(1).receives).toBe(false)
  })

  it('keeps a stored highlight mode', async () => {
    mount([widget(1, { broadcasts: true, receives: true, receiveMode: 'highlight' })],
          vi.fn(), 1)
    await waitFor(() => expect(read(1)).not.toBeNull())
    expect(read(1).receiveMode).toBe('highlight')
  })

  it('does not write anything just because the panel was opened', async () => {
    const persist = mount([widget(1)], vi.fn(), 1)
    await waitFor(() => expect(read(1)).not.toBeNull())
    // Defaulting is a local convenience, not a change the user made. Saving it
    // would rewrite every widget config the moment someone clicks a tile.
    expect(persist).not.toHaveBeenCalled()
  })
})

describe('a change the user makes is written down', () => {
  it('persists the new interaction', async () => {
    const persist = mount([widget(1, { broadcasts: true, receives: true })], vi.fn(), 1)
    fireEvent.click(screen.getByRole('button', { name: /receive only/i }))
    await waitFor(() => expect(persist).toHaveBeenCalled())
    const [id, interaction] = persist.mock.calls.at(-1)!
    expect(id).toBe(1)
    expect(interaction.broadcasts).toBe(false)
  })

  it('persists the widget id it belongs to', async () => {
    const persist = mount([widget(1), widget(7, { broadcasts: true, receives: true })],
                          vi.fn(), 7)
    fireEvent.click(screen.getByRole('button', { name: /receive only/i }))
    await waitFor(() => expect(persist).toHaveBeenCalled())
    expect(persist.mock.calls.at(-1)![0]).toBe(7)
  })
})
