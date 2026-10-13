import { useId } from 'react'
import { RobotDefs, RobotHeadArt } from '../../pages/ask/AskRobot'

/**
 * The Ask AI robot's head as the assistant's avatar on a chat card (step 10,
 * Part B): head, visor, eyes, ear rings and antenna, no body.
 *
 * `state` is this message's: `thinking` while its question runs, `happy` or
 * `error` for a moment when it comes back, `idle` after. `live` is the newest
 * message: only that head moves (and then only its eyes blink when idle: no
 * routine, no pointer, no sleep). Older heads are still.
 *
 * Decorative: the card's own text says what happened.
 */
export type HeadState = 'idle' | 'thinking' | 'happy' | 'error'

export default function RobotHead({ state = 'idle', live = false }: { state?: HeadState; live?: boolean }) {
  const uid = useId().replace(/:/g, '')
  return (
    <span className="dl-bot dl-bot--head" data-state={state} data-live={live ? '' : undefined} aria-hidden="true">
      <svg viewBox="38 10 224 174" focusable="false">
        <RobotDefs uid={uid} />
        <RobotHeadArt uid={uid} />
      </svg>
    </span>
  )
}
