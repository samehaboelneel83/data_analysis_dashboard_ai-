import { useSyncExternalStore } from 'react'

/**
 * What the Ask AI page tells its robot. The page and the chat report what
 * happened (`signalRobot`) and the picture reads the state (`useRobotMood`);
 * nothing in between re-renders.
 *
 *  - typing: while the question box has focus or text;
 *  - thinking: while a question runs;
 *  - happy / error: for a few seconds after it comes back;
 *  - idle otherwise. Sleep is the robot's own (AskRobot): it only happens
 *    while this says idle.
 */
export type RobotState = 'idle' | 'typing' | 'thinking' | 'happy' | 'error' | 'sleep'
/** `compose-on` / `compose-off`: the text box has focus or text, or neither.
 *  `key`: a keystroke in it. `running`: a question was sent. `answer` /
 *  `error`: how it came back. `rest`: the chat went away. */
export type RobotSignal = 'compose-on' | 'compose-off' | 'key' | 'running' | 'answer' | 'error' | 'rest'

/** How long the reaction to an answer or an error lasts. */
export const REACTION_MS = 3500

export interface RobotMood { state: RobotState; /** Goes up by one on each keystroke: a nod. */ nod: number }

let composing = false
let reaction: 'thinking' | 'happy' | 'error' | null = null
let nod = 0
let timer: ReturnType<typeof setTimeout> | undefined
let snap: RobotMood = { state: 'idle', nod: 0 }
const listeners = new Set<() => void>()

function publish() {
  const state: RobotState = reaction ?? (composing ? 'typing' : 'idle')
  if (state === snap.state && nod === snap.nod) return
  snap = { state, nod }
  listeners.forEach(l => l())
}

function react(next: typeof reaction, ms?: number) {
  clearTimeout(timer)
  timer = ms ? setTimeout(() => { timer = undefined; reaction = null; publish() }, ms) : undefined
  reaction = next
}

export function signalRobot(signal: RobotSignal) {
  if (signal === 'compose-on') composing = true
  else if (signal === 'compose-off') composing = false
  else if (signal === 'key') nod += 1
  else if (signal === 'running') react('thinking')
  else if (signal === 'answer') react('happy', REACTION_MS)
  else if (signal === 'error') react('error', REACTION_MS)
  else { react(null); composing = false }
  publish()
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
const current = () => snap

export function useRobotMood(): RobotMood {
  return useSyncExternalStore(subscribe, current, current)
}
