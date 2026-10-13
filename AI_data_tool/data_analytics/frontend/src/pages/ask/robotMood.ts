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
 *  `error`: how it came back. `rest`: the chat went away. `look-on` /
 *  `look-off`: the pointer is over the data chooser, or left it. `chosen`: a
 *  dataset or connection was picked (a short cheer). */
export type RobotSignal = 'compose-on' | 'compose-off' | 'key' | 'running' | 'answer' | 'error' | 'rest'
  | 'look-on' | 'look-off' | 'chosen'

/** How long the reaction to an answer or an error lasts. */
export const REACTION_MS = 3500
/** How long the cheer at choosing the data lasts. */
export const CHEER_MS = 1600

export interface RobotMood {
  state: RobotState
  /** Goes up by one on each keystroke: a nod. */
  nod: number
  /** The pointer is over the data chooser: an idle robot looks that way. */
  look: boolean
  /** The happy state is the small cheer at choosing the data, not an answer. */
  cheer: boolean
}

let composing = false
let reaction: 'thinking' | 'happy' | 'error' | null = null
let nod = 0
let look = false
let cheer = false
let timer: ReturnType<typeof setTimeout> | undefined
let snap: RobotMood = { state: 'idle', nod: 0, look: false, cheer: false }
const listeners = new Set<() => void>()

function publish() {
  const state: RobotState = reaction ?? (composing ? 'typing' : 'idle')
  if (state === snap.state && nod === snap.nod && look === snap.look && cheer === snap.cheer) return
  snap = { state, nod, look, cheer }
  listeners.forEach(l => l())
}

function react(next: typeof reaction, ms?: number) {
  clearTimeout(timer)
  timer = ms ? setTimeout(() => { timer = undefined; reaction = null; cheer = false; publish() }, ms) : undefined
  reaction = next
  cheer = false
}

export function signalRobot(signal: RobotSignal) {
  if (signal === 'compose-on') composing = true
  else if (signal === 'compose-off') composing = false
  else if (signal === 'key') nod += 1
  else if (signal === 'running') react('thinking')
  else if (signal === 'answer') react('happy', REACTION_MS)
  else if (signal === 'error') react('error', REACTION_MS)
  else if (signal === 'look-on') look = true
  else if (signal === 'look-off') look = false
  else if (signal === 'chosen') { react('happy', CHEER_MS); cheer = true; composing = false; look = false }
  // The chat went away. A cheer for the data just chosen outlives the old chat.
  else { if (!cheer) react(null); composing = false; look = false }
  publish()
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
const current = () => snap

export function useRobotMood(): RobotMood {
  return useSyncExternalStore(subscribe, current, current)
}
