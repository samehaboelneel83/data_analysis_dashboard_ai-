import { describe, it, expect } from 'vitest'
import { placePopup } from './DataPicker'

/**
 * The hero picker sits low on the page; opening its list downward pushed it
 * off-screen and the user had to scroll to see the options. It must flip up
 * when there is no room below, and the list must shrink to fit either way.
 */
const rect = (top: number, height = 56) =>
  ({ top, bottom: top + height, height, left: 0, right: 600, width: 600, x: 0, y: top, toJSON: () => ({}) }) as DOMRect

describe('placePopup', () => {
  it('opens downward when the list fits below', () => {
    const p = placePopup(rect(60), { top: 50, bottom: 800 })
    expect(p.up).toBe(false)
    expect(p.listMax).toBe(340)
  })

  it('flips up when the trigger is near the bottom of the pane', () => {
    // The real case: a 683px window, picker at ~440px.
    const p = placePopup(rect(440), { top: 50, bottom: 683 })
    expect(p.up).toBe(true)
    // Shrunk to the room above so the whole popup stays on screen.
    expect(p.listMax).toBeLessThanOrEqual(440 - 50 - 12 - 110)
  })

  it('stays down, but shorter, when below still has more room than above', () => {
    const p = placePopup(rect(120), { top: 50, bottom: 520 })
    expect(p.up).toBe(false)
    expect(p.listMax).toBe(520 - 176 - 12 - 110)
  })

  it('stays down when a comfortable list fits below, even with more room above', () => {
    // Hero picker under the headline on a short window: down keeps the
    // headline visible; 310px below gives a 200px list.
    const p = placePopup(rect(400), { top: 50, bottom: 778 })
    expect(p.up).toBe(false)
    expect(p.listMax).toBe(778 - 456 - 12 - 110)
  })

  it('never shrinks the list below a usable height', () => {
    expect(placePopup(rect(100), { top: 90, bottom: 200 }).listMax).toBe(120)
  })
})
