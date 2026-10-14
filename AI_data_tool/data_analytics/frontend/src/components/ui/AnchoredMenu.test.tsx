import { describe, it, expect, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import { createRef } from 'react'
import AnchoredMenu from './AnchoredMenu'

/** QA5 F2: the field pop-ups are portalled and kept inside the window. */
function anchorAt(left: number, top: number) {
  const ref = createRef<HTMLButtonElement>()
  const btn = document.createElement('button')
  btn.getBoundingClientRect = () => ({ left, top, right: left + 20, bottom: top + 20, width: 20, height: 20, x: left, y: top, toJSON: () => ({}) })
  document.body.append(btn)
  ;(ref as { current: HTMLButtonElement | null }).current = btn
  return ref
}
const size = (w: number, h: number) => {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => w })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => h })
}

describe('AnchoredMenu (QA5 F2)', () => {
  const ow = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth')!
  const oh = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')!
  afterEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', ow)
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', oh)
    document.querySelectorAll('body > button').forEach(b => b.remove())
  })

  it('renders on <body>, under its button', () => {
    size(150, 100)
    const { container } = render(<div style={{ overflow: 'hidden' }}><AnchoredMenu anchorRef={anchorAt(100, 100)}>x</AnchoredMenu></div>)
    expect(container.querySelector('[role=menu]')).toBeNull()
    const m = document.body.querySelector('[role=menu]') as HTMLElement
    expect(m.style.position).toBe('fixed')
    expect(m.style.top).toBe('124px')
    expect(m.style.left).toBe('100px')
  })

  it('flips above when there is no room below, and shifts back inside the window', () => {
    size(200, 300)
    render(<AnchoredMenu anchorRef={anchorAt(window.innerWidth - 30, window.innerHeight - 40)}>x</AnchoredMenu>)
    const m = document.body.querySelector('[role=menu]') as HTMLElement
    expect(parseFloat(m.style.top) + 300).toBeLessThanOrEqual(window.innerHeight - 8)
    expect(parseFloat(m.style.left) + 200).toBeLessThanOrEqual(window.innerWidth - 8)
  })

  it('in Arabic it aligns to the button\'s right edge', () => {
    size(150, 100)
    render(<AnchoredMenu anchorRef={anchorAt(500, 100)} rtl>x</AnchoredMenu>)
    const m = document.body.querySelector('[role=menu]') as HTMLElement
    expect(m.style.left).toBe(`${520 - 150}px`)
  })
})
