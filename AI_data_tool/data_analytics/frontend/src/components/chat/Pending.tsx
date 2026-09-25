import { useEffect, useRef, useState } from 'react'
import { useT, type MessageKey } from '../../i18n'

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
 *  the wait is past anything ordinary it says what is taking the time. */

//: Past this, the wait stops being ordinary and deserves an explanation rather
//: than a spinner. Every non-dashboard question measured on this data answered
//: inside 21 seconds.
const UNUSUAL_AFTER_S = 20

function readable(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

/** Is this the question that takes minutes? Matched on the words a person
 *  actually types, the same way the agent's own intent check does. */
function isDashboardRequest(question: string): boolean {
  const q = (question || '').toLowerCase()
  return q.includes('dashboard') &&
    /suggest|propose|recommend|build|create|make|design|give me|show me|i need|i want/.test(q)
}

/** The four stages a question goes through, shown as a checklist so the wait
 *  has a shape. The server does not stream its progress, so the checklist
 *  advances on typical timings and never claims to be done: the last stage
 *  stays "in progress" until the answer actually arrives. */
const STAGES: { key: MessageKey; at: number }[] = [
  { key: 'ask.stage.understand', at: 0 },
  { key: 'ask.stage.query', at: 2 },
  { key: 'ask.stage.run', at: 5 },
  { key: 'ask.stage.chart', at: 10 },
]

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
  const current = STAGES.reduce((acc, s, i) => (seconds >= s.at ? i : acc), 0)

  return (
    <div
      role="status"
      // polite, not assertive: a counter that interrupts a screen reader every
      // second is worse than no counter at all.
      aria-live="polite"
      className="dl-pending">
      <div className="dl-pending__head">
        <span className="dl-pending__pulse" aria-hidden />
        <span className="dl-pending__title">
          {designing ? 'Designing dashboards' : t('ask.analyzing')}
        </span>
        <span className="dl-pending__time" dir="ltr">
          {designing ? '' : 'Thinking · '}{readable(seconds)}
        </span>
      </div>
      {!designing && (
        <ol className="dl-pending__steps">
          {STAGES.map((s, i) => (
            <li key={s.key} className={i < current ? 'is-done' : i === current ? 'is-now' : ''}>
              <span className="dl-pending__dot" aria-hidden />
              {t(s.key)}
            </li>
          ))}
        </ol>
      )}
      <div className="dl-pending__skeleton" aria-hidden>
        <span style={{ width: '72%' }} /><span style={{ width: '54%' }} />
        <span className="dl-pending__skeleton-chart" />
      </div>
      {unusual && (
        <div className="dl-pending__note">
          {designing
            ? 'Each dashboard’s query is being checked against your database, and '
              + 'repaired if it does not run. This can take a few minutes.'
            : 'Still working — the query is being checked against your database.'}
        </div>
      )}
    </div>
  )
}
