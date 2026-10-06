import { useEffect, useRef, useState } from 'react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/** What the chat shows between pressing Send and the answer arriving.
 *
 *  Measured on the real Moodle connection, "suggest a dashboard for me" takes 25
 *  seconds on a good run and 340 on a bad one: it designs three dashboards, runs
 *  each proposed query against the database, and repairs the ones that fail. All
 *  of that is work worth doing. None of it was visible — the Send button greyed
 *  out and nothing else happened, sometimes for minutes.
 *
 *  A person cannot tell a slow answer from a hung one. They press Send again, or
 *  reload, and lose the answer that was about to arrive. So this counts, and once
 *  the wait is past anything ordinary it says what is taking the time.
 *
 *  Redesign 4b: the timer-driven checklist ("Writing the query", "Running
 *  it"…) is gone. The server does not stream its progress, so those stages
 *  were guesses dressed as facts; the elapsed time and a typical range are
 *  what is actually known. */

//: Past this, the wait stops being ordinary and deserves an explanation rather
//: than a spinner. Every non-dashboard question measured on this data answered
//: inside 21 seconds.
const UNUSUAL_AFTER_S = 20

/** Is this the question that takes minutes? Matched on the words a person
 *  actually types, the same way the agent's own intent check does. */
function isDashboardRequest(question: string): boolean {
  const q = (question || '').toLowerCase()
  return q.includes('dashboard') &&
    /suggest|propose|recommend|build|create|make|design|give me|show me|i need|i want/.test(q)
}

export default function Pending({ question }: { question: string }) {
  const t = useT()
  const [seconds, setSeconds] = useState(0)
  const started = useRef(Date.now())

  useEffect(() => {
    const id = setInterval(
      () => setSeconds(Math.floor((Date.now() - started.current) / 1000)), 1000)
    // Cleared on unmount: a leaked interval writing to a component that is gone
    // is a console error in React and a slow leak in a long chat session.
    return () => clearInterval(id)
  }, [])

  const unusual = seconds > UNUSUAL_AFTER_S
  const designing = isDashboardRequest(question)
  const time = localDigits(seconds < 60
    ? t('pend.secs', { n: seconds })
    : t('pend.mins', { m: Math.floor(seconds / 60), s: seconds % 60 }))

  return (
    <div
      role="status"
      // polite, not assertive: a counter that interrupts a screen reader every
      // second is worse than no counter at all.
      aria-live="polite"
      className="dl-pending">
      <div className="dl-pending__head">
        <span className="dl-pending__pulse" aria-hidden><i /><i /><i /></span>
        <span className="dl-pending__title">{designing ? t('pend.designing') : t('ask.analyzing')}</span>
        <span className="dl-pending__time">{time}</span>
      </div>
      <div className="dl-pending__skeleton" aria-hidden>
        <span style={{ width: '72%' }} /><span style={{ width: '54%' }} />
        <span className="dl-pending__skeleton-chart" />
      </div>
      <div className="dl-pending__note">
        {unusual
          ? (designing ? t('pend.slowDashboards') : t('pend.slow'))
          : t('pend.usual')}
      </div>
    </div>
  )
}
