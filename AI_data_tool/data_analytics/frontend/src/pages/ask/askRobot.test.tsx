import { renderWithProviders as render, screen, fireEvent, act } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import AskRobot, { SLEEP_AFTER_MS } from './AskRobot'
import AskIllustration from './AskIllustration'
import ChatPane from '../../components/chat/ChatPane'
import { agentApi } from '../../services/api'
import { signalRobot, REACTION_MS } from './robotMood'
import { translate } from '../../i18n'

/** Step 10: the robot -- its parts, what the page tells it, and its own life
 *  (the idle routine, sleep, the timers it must not leave behind). */

const bot = (c: HTMLElement) => c.querySelector('.dl-bot') as HTMLElement
const shown = (c: HTMLElement) => bot(c).getAttribute('data-state')
/** Let the awaits inside ChatPane's send settle, without moving the clock. */
const settle = () => act(async () => { for (let i = 0; i < 20; i++) await Promise.resolve() })

beforeEach(() => { vi.useFakeTimers(); signalRobot('rest') })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('the robot picture', () => {
  it('is the full stage on the empty page: aura, orbits, links, packets, sparks and four cards', () => {
    const { container } = render(<AskRobot />)
    for (const part of ['aura', 'net', 'o1', 'o2', 'c-bars', 'c-donut', 'c-chat', 'c-table']) {
      expect(container.querySelector(`.dl-ill__${part}`), part).not.toBeNull()
    }
    expect(container.querySelectorAll('.dl-ill__link')).toHaveLength(4)
    expect(container.querySelectorAll('.dl-ill__pkt')).toHaveLength(4)
    expect(container.querySelectorAll('.dl-ill__spark')).toHaveLength(4)
    for (const part of ['float', 'act', 'tilt', 'head', 'ears', 'visor', 'gaze', 'look', 'eyes', 'torso', 'arm--l', 'arm--r', 'leg--l', 'leg--r']) {
      expect(container.querySelector(`g.dl-bot__${part}`), part).not.toBeNull()
    }
  })

  it('is the robot alone in the step-2 hero', () => {
    const { container } = render(<AskRobot bare />)
    expect(bot(container)).toBeInTheDocument()
    for (const part of ['aura', 'net', 'card', 'spark', 'link', 'pkt']) {
      expect(container.querySelector(`.dl-ill__${part}`), part).toBeNull()
    }
  })

  it('is a button with a translated label, and everything else is hidden from screen readers', () => {
    const { container } = render(<AskRobot />)
    expect(screen.getByRole('button', { name: translate('en', 'ask2.robot.label') })).toBe(bot(container))
    expect(translate('ar', 'ask2.robot.label')).not.toBe(translate('en', 'ask2.robot.label'))
    const stage = container.querySelector('.dl-ill__stage')!
    expect([...stage.children].filter(el => el !== bot(container) && el.getAttribute('aria-hidden') !== 'true')).toEqual([])
    expect(bot(container).querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('shows the state it is given, on the robot and on the stage', () => {
    for (const state of ['idle', 'typing', 'thinking', 'happy', 'error', 'sleep'] as const) {
      const { container, unmount } = render(<AskRobot state={state} />)
      expect(shown(container)).toBe(state)
      expect(container.querySelector('.dl-ill')).toHaveAttribute('data-state', state)
      unmount()
    }
  })
})

describe('what the page tells the robot', () => {
  beforeEach(() => {
    vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
    vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  })
  const page = () => render(<><AskIllustration /><ChatPane dataSourceId={2} onActivity={signalRobot} /></>)
  const box = () => screen.getByPlaceholderText(/ask/i)

  it('typing while the question box has focus or text', async () => {
    const { container } = page()
    await settle()
    expect(shown(container)).toBe('idle')
    fireEvent.focus(box())
    expect(shown(container)).toBe('typing')
    fireEvent.change(box(), { target: { value: 'total' } })
    fireEvent.blur(box())
    expect(shown(container)).toBe('typing') // text, no focus
    fireEvent.change(box(), { target: { value: '' } })
    expect(shown(container)).toBe('idle')
  })

  it('nods on each keystroke', async () => {
    const { container } = page()
    await settle()
    fireEvent.change(box(), { target: { value: 't' } })
    expect(bot(container)).toHaveAttribute('data-nod')
    act(() => { vi.advanceTimersByTime(300) })
    expect(bot(container)).not.toHaveAttribute('data-nod')
  })

  it('thinking while the question runs, happy at the answer with confetti, then idle', async () => {
    let answer!: (v: Awaited<ReturnType<typeof agentApi.ask>>) => void
    vi.spyOn(agentApi, 'ask').mockReturnValue(new Promise(r => { answer = r }))
    const { container } = page()
    await settle()
    fireEvent.change(box(), { target: { value: 'total sales' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await settle()
    expect(shown(container)).toBe('thinking')
    act(() => { vi.advanceTimersByTime(60_000) })
    expect(shown(container)).toBe('thinking') // as long as it runs; never asleep
    answer({ run_id: 1, status: 'ok', answer: 'Done.', intent: null, error: null })
    await settle()
    expect(shown(container)).toBe('happy')
    expect(container.querySelectorAll('.dl-ill__fx i')).toHaveLength(28)
    act(() => { vi.advanceTimersByTime(REACTION_MS) })
    expect(shown(container)).toBe('idle')
    expect(container.querySelectorAll('.dl-ill__fx i')).toHaveLength(0)
  })

  it('error when the answer failed or the request did, then idle', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValueOnce({ run_id: 1, status: 'failed', answer: null, intent: null, error: 'bad sql' })
      .mockRejectedValueOnce(new Error('down'))
    const { container } = page()
    await settle()
    for (const q of ['one', 'two']) {
      fireEvent.change(box(), { target: { value: q } })
      fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
      await settle()
      expect(shown(container)).toBe('error')
      expect(container.querySelector('.dl-ill__fx i')).toBeNull()
      act(() => { vi.advanceTimersByTime(REACTION_MS) })
      expect(shown(container)).toBe('idle')
    }
  })

  it('rests when the chat goes away', async () => {
    const { container, rerender } = page()
    await settle()
    fireEvent.focus(box())
    expect(shown(container)).toBe('typing')
    rerender(<AskIllustration />)
    expect(shown(container)).toBe('idle')
  })
})

describe("the robot's own life", () => {
  it('sleeps after 20s with no activity, and any activity wakes it wide-eyed', () => {
    const { container } = render(<AskRobot />)
    act(() => { vi.advanceTimersByTime(SLEEP_AFTER_MS - 1) })
    expect(shown(container)).toBe('idle')
    act(() => { vi.advanceTimersByTime(1) })
    expect(shown(container)).toBe('sleep')
    expect(container.querySelector('.dl-ill')).toHaveAttribute('data-state', 'sleep')
    act(() => { fireEvent.keyDown(window, { key: 'a' }) })
    expect(shown(container)).toBe('idle')
    expect(bot(container)).toHaveAttribute('data-wake')
    act(() => { vi.advanceTimersByTime(700) })
    expect(bot(container)).not.toHaveAttribute('data-wake')
  })

  it('stays awake while there is activity: pointer, key or scroll', () => {
    const { container } = render(<AskRobot />)
    for (const poke of [() => fireEvent.pointerMove(window), () => fireEvent.keyDown(window), () => fireEvent.scroll(document)]) {
      act(() => { vi.advanceTimersByTime(SLEEP_AFTER_MS - 1000); poke() })
    }
    expect(shown(container)).toBe('idle')
    act(() => { vi.advanceTimersByTime(SLEEP_AFTER_MS) })
    expect(shown(container)).toBe('sleep')
  })

  it('never sleeps unless idle, and a state from the page wakes it', () => {
    const { container, rerender } = render(<AskRobot state="typing" />)
    act(() => { vi.advanceTimersByTime(SLEEP_AFTER_MS * 3) })
    expect(shown(container)).toBe('typing')
    rerender(<AskRobot state="idle" />)
    act(() => { vi.advanceTimersByTime(SLEEP_AFTER_MS) })
    expect(shown(container)).toBe('sleep')
    rerender(<AskRobot state="thinking" />)
    expect(shown(container)).toBe('thinking')
    rerender(<AskRobot state="idle" />)
    expect(shown(container)).toBe('idle')
  })

  it('does a move of its own every 6-9s while idle, and none while the page has a state', () => {
    const random = vi.spyOn(Math, 'random').mockReturnValue(0) // the soonest, the first move
    const { container, rerender } = render(<AskRobot />)
    act(() => { vi.advanceTimersByTime(5999) })
    expect(bot(container)).not.toHaveAttribute('data-act')
    act(() => { vi.advanceTimersByTime(1) })
    expect(bot(container)).toHaveAttribute('data-act', 'wave')
    act(() => { vi.advanceTimersByTime(1800) })
    expect(bot(container)).not.toHaveAttribute('data-act')
    random.mockReturnValue(0.999) // the last move
    act(() => { vi.advanceTimersByTime(6000 - 1800) })
    expect(bot(container)).toHaveAttribute('data-act', 'spin')
    rerender(<AskRobot state="thinking" />)
    expect(bot(container)).not.toHaveAttribute('data-act')
    act(() => { vi.advanceTimersByTime(30_000) })
    expect(bot(container)).not.toHaveAttribute('data-act')
  })

  it('pauses the routine and the sleep clock while the tab is hidden', () => {
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    const { container } = render(<AskRobot />)
    act(() => { fireEvent(document, new Event('visibilitychange')) })
    expect(vi.getTimerCount()).toBe(0)
    act(() => { vi.advanceTimersByTime(60_000) })
    expect(shown(container)).toBe('idle')
    expect(bot(container)).not.toHaveAttribute('data-act')
    hidden.mockReturnValue(false)
    act(() => { fireEvent(document, new Event('visibilitychange')) })
    expect(vi.getTimerCount()).toBe(2) // the routine and the sleep clock
  })

  it('a click does a spin or a jump with a burst of sparks; hovering is marked', () => {
    const { container } = render(<AskRobot />)
    fireEvent.click(bot(container))
    expect(['spin', 'jump']).toContain(bot(container).getAttribute('data-act'))
    expect(container.querySelectorAll('.dl-ill__fx b')).toHaveLength(12)
    act(() => { vi.advanceTimersByTime(1500) })
    expect(container.querySelector('.dl-ill__fx b')).toBeNull()
    expect(bot(container)).not.toHaveAttribute('data-act')
    fireEvent.pointerEnter(bot(container))
    expect(bot(container)).toHaveAttribute('data-hover')
    fireEvent.pointerLeave(bot(container))
    expect(bot(container)).not.toHaveAttribute('data-hover')
  })

  it('follows the pointer with its eyes only while idle, and never a touch', () => {
    const { container, rerender } = render(<AskRobot />)
    const gaze = () => (container.querySelector('.dl-bot__gaze') as SVGGElement).style.transform
    // jsdom has no PointerEvent: a mouse event carrying the pointer's fields.
    const move = (pointerType: string) => fireEvent(window, Object.assign(
      new MouseEvent('pointermove', { clientX: 5000, clientY: 5000 }), { pointerType }))
    move('mouse')
    expect(gaze()).toBe('translate(9.0px,7.0px)')
    rerender(<AskRobot state="typing" />)
    expect(gaze()).toBe('')
    move('mouse')
    expect(gaze()).toBe('')
    rerender(<AskRobot />)
    move('touch')
    expect(gaze()).toBe('')
  })

  it('leaves no timer behind when it unmounts', () => {
    const { container, unmount } = render(<AskRobot state="happy" nod={0} />)
    fireEvent.pointerMove(window)
    expect(container.querySelectorAll('.dl-ill__fx i').length).toBeGreaterThan(0)
    expect(vi.getTimerCount()).toBeGreaterThan(0)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
    const sleeper = render(<AskRobot />)
    act(() => { vi.advanceTimersByTime(SLEEP_AFTER_MS) })
    act(() => { fireEvent.keyDown(window); fireEvent.click(bot(sleeper.container)) })
    sleeper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('is a still picture under reduced motion: no button, packets, routine, nod or confetti', () => {
    const real = window.matchMedia
    window.matchMedia = ((q: string) => ({ ...real(q), matches: q.includes('prefers-reduced-motion') })) as typeof window.matchMedia
    try {
      const { container, rerender } = render(<AskRobot />)
      expect(screen.queryByRole('button')).toBeNull()
      expect(bot(container)).toHaveAttribute('aria-hidden', 'true')
      expect(container.querySelector('.dl-ill__pkt')).toBeNull()
      act(() => { vi.advanceTimersByTime(15_000) })
      expect(bot(container)).not.toHaveAttribute('data-act')
      rerender(<AskRobot nod={1} />)
      expect(bot(container)).not.toHaveAttribute('data-nod')
      rerender(<AskRobot state="happy" nod={1} />)
      expect(container.querySelector('.dl-ill__fx i')).toBeNull()
    } finally { window.matchMedia = real }
  })
})

describe('the robot CSS', () => {
  const css = fs.readFileSync(path.join(__dirname, 'askLayout.css'), 'utf8')
  const picture = css.slice(css.indexOf('The picture: the stage'), css.indexOf('Data picker'))

  it('animates transform and opacity only', () => {
    const frames = [...picture.matchAll(/@keyframes [\w-]+ \{([\s\S]*?\})\s*\}/g)].map(m => m[1])
    expect(frames.length).toBeGreaterThan(30)
    const props = new Set(frames.flatMap(f => [...f.matchAll(/([a-z-]+)\s*:/g)].map(m => m[1])))
    expect([...props].sort()).toEqual(['opacity', 'transform'])
    const moved = [...picture.matchAll(/transition:\s*([^;}]+)/g)]
      .flatMap(m => m[1].replace(/\([^)]*\)/g, '').split(',').map(p => p.trim().split(' ')[0]))
    expect([...new Set(moved)].sort()).toEqual(['opacity', 'transform'])
  })

  it('uses tokens, never a literal colour', () => {
    expect(picture.match(/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(|\b(white|black)\b/gi)).toBeNull()
  })

  it('mirrors in Arabic and is still under reduced motion', () => {
    expect(css).toMatch(/\[dir="rtl"\] \.dl-ill__stage \{ transform: scaleX\(-1\); \}/)
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(reduced).toMatch(/\.dl-ill \*[^{]*\{ animation: none !important; transition: none !important; \}/)
    expect(reduced).toMatch(/\.dl-ill \*::before, \.dl-ill \*::after \{ animation: none !important; transition: none !important; \}/)
    expect(reduced).toMatch(/\.dl-ill__pkt, \.dl-ill__fx \{ display: none; \}/)
  })
})
