import { renderWithProviders as render, screen, fireEvent, waitFor, act } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import AskIllustration from './AskIllustration'
import ChatPane from '../../components/chat/ChatPane'
import { agentApi } from '../../services/api'
import { signalRobot, MOOD_MS } from './robotMood'

/** Step 10: the robot -- its parts, its moods, and what the chat tells it. */

const bot = (c: HTMLElement) => c.querySelector('.dl-bot') as SVGElement
const mood = (c: HTMLElement) => bot(c).getAttribute('data-mood')

beforeEach(() => { vi.useFakeTimers(); signalRobot('rest') })
afterEach(() => { vi.useRealTimers() })

describe('the robot picture', () => {
  it('draws each moving part as its own group, hidden from screen readers', () => {
    const { container } = render(<AskIllustration />)
    expect(bot(container)).toHaveAttribute('aria-hidden', 'true')
    for (const part of ['head', 'ears', 'visor', 'eyes', 'torso', 'arm--l', 'arm--r', 'legs']) {
      expect(container.querySelector(`g.dl-bot__${part}`), part).not.toBeNull()
    }
    expect(container.querySelectorAll('g.dl-bot__eye')).toHaveLength(2)
    expect(container.querySelectorAll('.dl-ill__card')).toHaveLength(5)
  })

  it('is alone, without the cards, in the small hero', () => {
    const { container } = render(<AskIllustration small />)
    expect(bot(container)).toBeInTheDocument()
    expect(container.querySelector('.dl-ill__card')).toBeNull()
    expect(container.querySelector('.dl-ill__lines')).toBeNull()
  })

  it('carries where the reader types', () => {
    expect(bot(render(<AskIllustration look="side" />).container)).toHaveAttribute('data-look', 'side')
    expect(bot(render(<AskIllustration small />).container)).toHaveAttribute('data-look', 'down')
  })
})

describe('the robot moods', () => {
  it('looks while the reader types, then goes back to idle', () => {
    const { container } = render(<AskIllustration />)
    expect(mood(container)).toBe('idle')
    act(() => signalRobot('typing'))
    expect(mood(container)).toBe('typing')
    // Each key keeps it looking; it rests only after the last one.
    act(() => { vi.advanceTimersByTime(MOOD_MS.typing - 100); signalRobot('typing') })
    act(() => { vi.advanceTimersByTime(MOOD_MS.typing - 100) })
    expect(mood(container)).toBe('typing')
    act(() => { vi.advanceTimersByTime(200) })
    expect(mood(container)).toBe('idle')
  })

  it('thinks for as long as the question runs, and typing does not interrupt', () => {
    const { container } = render(<AskIllustration />)
    act(() => signalRobot('running'))
    act(() => { vi.advanceTimersByTime(60_000); signalRobot('typing') })
    expect(mood(container)).toBe('thinking')
  })

  it('is happy at an answer and tilts at an error, each for a few seconds', () => {
    const { container } = render(<AskIllustration />)
    act(() => { signalRobot('running'); signalRobot('answer') })
    expect(mood(container)).toBe('happy')
    act(() => { vi.advanceTimersByTime(MOOD_MS.happy) })
    expect(mood(container)).toBe('idle')
    act(() => { signalRobot('running'); signalRobot('error') })
    expect(mood(container)).toBe('error')
    act(() => { vi.advanceTimersByTime(MOOD_MS.error) })
    expect(mood(container)).toBe('idle')
  })
})

describe('what the chat tells the robot', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
    vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  })
  const ask = (onActivity: (what: string) => void) => {
    const view = render(<ChatPane dataSourceId={2} onActivity={onActivity} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'total sales' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    return view
  }

  it('typing, running, then the answer; rest when the chat goes away', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 1, status: 'ok', answer: 'Done.', intent: null, error: null })
    const seen: string[] = []
    const { unmount } = ask(w => seen.push(w))
    await waitFor(() => expect(seen).toEqual(['typing', 'running', 'answer']))
    unmount()
    expect(seen.at(-1)).toBe('rest')
  })

  it('an answer that failed, or a request that did, is an error', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 1, status: 'failed', answer: null, intent: null, error: 'bad sql' })
    const seen: string[] = []
    ask(w => seen.push(w)).unmount()
    await waitFor(() => expect(seen).toContain('error'))

    vi.spyOn(agentApi, 'ask').mockRejectedValue(new Error('down'))
    const again: string[] = []
    ask(w => again.push(w))
    await waitFor(() => expect(again).toEqual(['typing', 'running', 'error']))
  })
})

describe('the robot CSS', () => {
  const css = fs.readFileSync(path.join(__dirname, 'askLayout.css'), 'utf8')
  const robot = css.slice(css.indexOf('The robot (AskRobot.tsx)'), css.indexOf('Data picker'))

  it('animates transform and opacity only', () => {
    const frames = [...robot.matchAll(/@keyframes [\w-]+ \{([\s\S]*?\})\s*\}/g)].map(m => m[1])
    expect(frames.length).toBeGreaterThan(6)
    const props = new Set(frames.flatMap(f => [...f.matchAll(/([a-z-]+)\s*:/g)].map(m => m[1])))
    expect([...props].sort()).toEqual(['opacity', 'transform'])
  })

  it('uses tokens, never a literal colour', () => {
    expect(robot.match(/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(/gi)).toBeNull()
  })

  it('mirrors in Arabic and stops under reduced motion', () => {
    expect(css).toMatch(/\[dir="rtl"\] \.dl-ill__stage \{ transform: scaleX\(-1\); \}/)
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(reduced).toMatch(/\.dl-ill \*[^{]*\{ animation: none !important; transition: none !important; \}/)
    expect(reduced).toMatch(/\.dl-bot \.dl-bot__head[^{]*\{ transform: none !important; \}/)
  })
})
