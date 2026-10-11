import { useSyncExternalStore } from 'react'

/**
 * What the Ask AI robot is doing. The page tells it what happened (`signal`)
 * and the picture reads the mood (`useRobotMood`); nothing in between
 * re-renders. Every mood but `thinking` wears off by itself, so the robot is
 * back to its idle loop a few seconds later.
 */
export type RobotMood = 'idle' | 'typing' | 'thinking' | 'happy' | 'error'
/** `typing`: a key in a text box. `running`: a question was sent. `answer` /
 *  `error`: how it came back. `rest`: the chat went away. */
export type RobotSignal = 'typing' | 'running' | 'answer' | 'error' | 'rest'

/** How long a mood lasts after its signal; `thinking` lasts as long as the run. */
export const MOOD_MS = { typing: 1600, happy: 3200, error: 3600 } as const

let mood: RobotMood = 'idle'
let timer: ReturnType<typeof setTimeout> | undefined
const listeners = new Set<() => void>()

function set(next: RobotMood, ms?: number) {
  clearTimeout(timer)
  timer = ms ? setTimeout(() => set('idle'), ms) : undefined
  if (next === mood) return
  mood = next
  listeners.forEach(l => l())
}

export function signalRobot(signal: RobotSignal) {
  if (signal === 'running') set('thinking')
  else if (signal === 'answer') set('happy', MOOD_MS.happy)
  else if (signal === 'error') set('error', MOOD_MS.error)
  else if (signal === 'rest') set('idle')
  // Typing never interrupts a run or the reaction to its answer.
  else if (mood === 'idle' || mood === 'typing') set('typing', MOOD_MS.typing)
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
const current = () => mood

export function useRobotMood(): RobotMood {
  return useSyncExternalStore(subscribe, current, current)
}
