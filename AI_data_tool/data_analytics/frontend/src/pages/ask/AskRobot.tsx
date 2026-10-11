import { useEffect, useId, useRef, useState, type Ref } from 'react'
import { useT } from '../../i18n'
import type { RobotState } from './robotMood'

/**
 * The Ask AI robot and its stage (step 10; a port of the approved prototype,
 * design-handoff-3/ask-ai/robot/ask-robot.html). The shapes, gradients,
 * transform origins and keyframe timings are the prototype's; the colours are
 * app tokens and the ids are classes (askLayout.css).
 *
 * `state` is the page's: idle, typing, thinking, happy, error (or sleep,
 * forced). The robot adds its own life on top:
 *
 *  - an idle routine: a random move every 6-9s, only while idle and while the
 *    tab is visible;
 *  - the eyes follow a mouse or pen while idle; hovering enlarges them; a
 *    click (or Enter / Space) does a spin or a jump with a burst of sparks;
 *  - a nod each time `nod` goes up (a keystroke);
 *  - sleep after 20s with no pointer, key or scroll activity while idle; any
 *    activity wakes it, wide-eyed;
 *  - confetti when it turns happy.
 *
 * `bare` is the step-2 hero: the robot alone, with no aura, orbits, links,
 * sparks or cards.
 *
 * Under prefers-reduced-motion nothing moves (CSS), and there is no routine,
 * gaze, nod, confetti or packets; the robot is then a plain picture, not a
 * button. Every timer and listener is dropped on unmount.
 */

const MOVES = ['wave', 'look', 'jump', 'dance', 'scan', 'stretch', 'spin'] as const
type Move = typeof MOVES[number]
const MOVE_MS: Record<Move, number> = { wave: 1800, look: 2400, jump: 800, dance: 2000, scan: 2200, stretch: 1800, spin: 1000 }
export const SLEEP_AFTER_MS = 20_000
const CONFETTI = ['var(--dl-series-1)', 'var(--dl-series-2)', 'var(--dl-series-3)', 'var(--dl-series-4)', 'var(--dl-bot-glow)']
const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/** The drawing's gradients, glow filter and visor clip; ids are per instance. */
export function RobotDefs({ uid }: { uid: string }) {
  return (
    <defs>
      <radialGradient id={`${uid}-body`} cx="35%" cy="25%" r="85%">
        <stop offset="0" className="dl-bot__s-hi" /><stop offset=".55" className="dl-bot__s-mid" /><stop offset="1" className="dl-bot__s-lo" />
      </radialGradient>
      <linearGradient id={`${uid}-visor`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" className="dl-bot__s-visor-hi" /><stop offset="1" className="dl-bot__s-visor-lo" />
      </linearGradient>
      <radialGradient id={`${uid}-eye`} cx="50%" cy="40%" r="60%">
        <stop offset="0" className="dl-bot__s-hi" /><stop offset=".35" className="dl-bot__s-glow" /><stop offset="1" className="dl-bot__s-accent" />
      </radialGradient>
      <linearGradient id={`${uid}-scan`} x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" className="dl-bot__s-glow" stopOpacity="0" /><stop offset=".5" className="dl-bot__s-glow" /><stop offset="1" className="dl-bot__s-glow" stopOpacity="0" />
      </linearGradient>
      <filter id={`${uid}-glow`} x="-80%" y="-80%" width="260%" height="260%">
        <feGaussianBlur stdDeviation="4" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
      </filter>
      <radialGradient id={`${uid}-shadow`}>
        <stop offset="0" className="dl-bot__s-shade" /><stop offset="1" className="dl-bot__s-shade" stopOpacity="0" />
      </radialGradient>
      <clipPath id={`${uid}-clip`}><rect x="80" y="62" width="140" height="96" rx="46" /></clipPath>
    </defs>
  )
}

/** The head: antenna, ear pods and rings, helmet, visor and every set of
 *  eyes. Shared with the chat's avatar (components/chat/RobotHead). */
export function RobotHeadArt({ uid, gaze }: { uid: string; gaze?: Ref<SVGGElement> }) {
  const url = (name: string) => `url(#${uid}-${name})`
  return (
    <g className="dl-bot__tilt"><g className="dl-bot__head">
      <rect className="dl-bot__joint" x="147" y="22" width="6" height="18" rx="3" />
      <circle className="dl-bot__bulb-ring" cx="150" cy="22" r="7" />
      <circle className="dl-bot__bulb" cx="150" cy="22" r="7" filter={url('glow')} />

      <g className="dl-bot__ears">
        <circle cx="60" cy="112" r="20" fill={url('body')} />
        <circle className="dl-bot__ear-ring dl-bot__ear-ring--l" cx="60" cy="112" r="12" filter={url('glow')} />
        <circle cx="240" cy="112" r="20" fill={url('body')} />
        <circle className="dl-bot__ear-ring dl-bot__ear-ring--r" cx="240" cy="112" r="12" filter={url('glow')} />
      </g>

      <rect x="62" y="34" width="176" height="146" rx="72" fill={url('body')} />
      <path className="dl-bot__shine" d="M92 58c22-18 62-22 92-12" strokeOpacity=".85" strokeWidth="7" />

      <g className="dl-bot__visor">
        <rect x="80" y="62" width="140" height="96" rx="46" fill={url('visor')} />
        <g clipPath={url('clip')}><rect className="dl-bot__scanline" x="80" y="108" width="140" height="5" fill={url('scan')} filter={url('glow')} /></g>
        <path className="dl-bot__shine" d="M98 78c14-8 34-11 52-9" strokeOpacity=".22" strokeWidth="6" />
        <rect className="dl-bot__visor-edge" x="80" y="62" width="140" height="96" rx="46" />
      </g>

      <g className="dl-bot__gaze" ref={gaze}><g className="dl-bot__look">
        <g className="dl-bot__eyes" filter={url('glow')}>
          <ellipse className="dl-bot__eye dl-bot__eye--l" cx="124" cy="110" rx="12" ry="13" fill={url('eye')} />
          <ellipse className="dl-bot__eye dl-bot__eye--r" cx="176" cy="110" rx="12" ry="13" fill={url('eye')} />
        </g>
        <g className="dl-bot__happy" filter={url('glow')}>
          <path d="M112 116q12-16 24 0" /><path d="M164 116q12-16 24 0" />
        </g>
        <g className="dl-bot__sleepy">
          <path d="M113 112q11 7 22 0" /><path d="M165 112q11 7 22 0" />
        </g>
        <g className="dl-bot__wow"><circle cx="124" cy="110" r="18" /><circle cx="176" cy="110" r="18" /></g>
      </g></g>
      <g className="dl-bot__dots" filter={url('glow')}>
        <circle cx="128" cy="112" r="6" /><circle cx="150" cy="112" r="6" /><circle cx="172" cy="112" r="6" />
      </g>
      <g className="dl-bot__orbiters" filter={url('glow')}>
        <circle cx="150" cy="-2" r="4" /><circle cx="262" cy="150" r="3" /><circle cx="40" cy="160" r="3.5" />
      </g>
      <g className="dl-bot__qmark">
        <circle cx="232" cy="40" r="17" />
        <text x="232" y="47" textAnchor="middle" fontSize="20" fontWeight="700">?</text>
      </g>
      <path className="dl-bot__sweat" d="M212 62c-4 6-6 9-6 12a6 6 0 0 0 12 0c0-3-2-6-6-12z" />
    </g></g>
  )
}

export default function AskRobot({ state = 'idle', nod = 0, bare = false }: {
  state?: RobotState
  nod?: number
  bare?: boolean
}) {
  const t = useT()
  const uid = useId().replace(/:/g, '')
  const url = (name: string) => `url(#${uid}-${name})`
  const robot = useRef<HTMLElement | null>(null)
  const gaze = useRef<SVGGElement>(null)
  const fx = useRef<HTMLDivElement>(null)
  const [asleep, setAsleep] = useState(false)
  const [reduced] = useState(reducedMotion)
  const shown: RobotState = state === 'idle' && asleep ? 'sleep' : state
  const shownRef = useRef(shown)
  shownRef.current = shown
  const engine = useRef<{ act: (m: Move) => void; clearAct: () => void; burst: (kind: 'confetti' | 'spark') => void; poke: () => void; arm: () => void } | null>(null)

  useEffect(() => {
    const R = robot.current!
    const once = new Set<ReturnType<typeof setTimeout>>()
    let routineTimer: ReturnType<typeof setTimeout> | undefined
    let idleTimer: ReturnType<typeof setTimeout> | undefined
    let actTimer: ReturnType<typeof setTimeout> | undefined
    let busy = false
    const later = (fn: () => void, ms: number) => {
      const id = setTimeout(() => { once.delete(id); fn() }, ms)
      once.add(id)
    }
    const clearAct = () => { delete R.dataset.act; busy = false; clearTimeout(actTimer); actTimer = undefined }
    const burst = (kind: 'confetti' | 'spark') => {
      const box = fx.current
      if (reduced || !box) return
      const n = kind === 'confetti' ? 28 : 12
      for (let i = 0; i < n; i++) {
        const e = document.createElement(kind === 'confetti' ? 'i' : 'b')
        const ang = Math.random() * Math.PI * 2
        const dist = (kind === 'confetti' ? 120 : 70) + Math.random() * 110
        e.style.setProperty('--dx', `${Math.cos(ang) * dist}px`)
        e.style.setProperty('--dy', `${Math.sin(ang) * dist - (kind === 'confetti' ? 60 : 20)}px`)
        e.style.setProperty('--rot', `${Math.random() * 720 - 360}deg`)
        if (kind === 'confetti') e.style.background = CONFETTI[i % CONFETTI.length]
        box.appendChild(e)
        later(() => e.remove(), 1500)
      }
    }
    const act = (m: Move) => {
      if (reduced || (shownRef.current !== 'idle' && shownRef.current !== 'typing')) return
      clearAct()
      void R.getBoundingClientRect() // restart the same move's animation
      R.dataset.act = m
      busy = true
      if (m === 'spin' || m === 'jump') burst('spark')
      actTimer = setTimeout(clearAct, MOVE_MS[m])
    }
    const routine = () => {
      clearTimeout(routineTimer)
      if (reduced) return
      routineTimer = setTimeout(() => {
        if (shownRef.current === 'idle' && !busy && !document.hidden) act(MOVES[Math.floor(Math.random() * MOVES.length)])
        routine()
      }, 6000 + Math.random() * 3000)
    }
    const arm = () => {
      clearTimeout(idleTimer)
      if (document.hidden) return
      idleTimer = setTimeout(() => { if (shownRef.current === 'idle') setAsleep(true) }, SLEEP_AFTER_MS)
    }
    const poke = () => {
      if (shownRef.current === 'sleep') {
        shownRef.current = 'idle'
        setAsleep(false)
        R.dataset.wake = ''
        later(() => { delete R.dataset.wake }, 700)
      }
      arm()
    }
    const onMove = (e: PointerEvent) => {
      poke()
      const g = gaze.current
      if (reduced || !g || e.pointerType === 'touch' || shownRef.current !== 'idle') return
      const b = R.getBoundingClientRect()
      let dx = (e.clientX - (b.left + b.width / 2)) / (window.innerWidth / 2)
      let dy = (e.clientY - (b.top + b.height * 0.3)) / (window.innerHeight / 2)
      if (R.closest('[dir="rtl"]')) dx = -dx // the stage is mirrored
      dx = Math.max(-1, Math.min(1, dx)); dy = Math.max(-1, Math.min(1, dy))
      g.style.transform = `translate(${(dx * 9).toFixed(1)}px,${(dy * 7).toFixed(1)}px)`
    }
    const onLeave = () => { if (gaze.current) gaze.current.style.transform = '' }
    const onVisible = () => {
      if (document.hidden) { clearTimeout(routineTimer); clearTimeout(idleTimer) } else { routine(); poke() }
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerdown', poke)
    window.addEventListener('keydown', poke)
    document.addEventListener('scroll', poke, { capture: true, passive: true })
    document.documentElement.addEventListener('mouseleave', onLeave)
    document.addEventListener('visibilitychange', onVisible)
    engine.current = { act, clearAct, burst, poke, arm }
    routine()
    arm()
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerdown', poke)
      window.removeEventListener('keydown', poke)
      document.removeEventListener('scroll', poke, { capture: true })
      document.documentElement.removeEventListener('mouseleave', onLeave)
      document.removeEventListener('visibilitychange', onVisible)
      clearTimeout(routineTimer); clearTimeout(idleTimer); clearTimeout(actTimer)
      once.forEach(clearTimeout)
      engine.current = null
    }
  }, [reduced])

  // A state from the page always wins over sleep.
  useEffect(() => { if (state !== 'idle') setAsleep(false) }, [state])

  // Each change of state ends the move under way; only idle eyes follow the
  // pointer; an answer gets confetti; back in idle, the sleep clock restarts.
  useEffect(() => {
    engine.current?.clearAct()
    if (shown !== 'idle' && gaze.current) gaze.current.style.transform = ''
    if (shown === 'happy') engine.current?.burst('confetti')
    if (shown === 'idle') engine.current?.arm()
  }, [shown])

  // A nod on each keystroke.
  const firstNod = useRef(true)
  useEffect(() => {
    if (firstNod.current) { firstNod.current = false; return }
    const R = robot.current
    if (reduced || !R) return
    delete R.dataset.nod
    void R.getBoundingClientRect()
    R.dataset.nod = ''
    const id = setTimeout(() => { delete R.dataset.nod }, 300)
    return () => clearTimeout(id)
  }, [nod, reduced])

  const press = () => {
    engine.current?.poke()
    if (shownRef.current === 'idle' || shownRef.current === 'typing') engine.current?.act(Math.random() < 0.5 ? 'spin' : 'jump')
  }
  const hover = (on: boolean) => { if (robot.current) { if (on) robot.current.dataset.hover = ''; else delete robot.current.dataset.hover } }

  const drawing = (
    <svg viewBox="0 0 300 380" aria-hidden="true" focusable="false">
      <RobotDefs uid={uid} />

      <ellipse className="dl-bot__shadow" cx="150" cy="366" rx="74" ry="11" fill={url('shadow')} />

      <g className="dl-bot__float"><g className="dl-bot__act">
        <g className="dl-bot__leg dl-bot__leg--l">
          <rect x="118" y="262" width="26" height="54" rx="13" fill={url('body')} />
          <rect className="dl-bot__joint" x="118" y="284" width="26" height="6" rx="3" />
          <path d="M108 330c0-12 10-20 23-20s23 8 23 20v4c0 3-2 5-5 5h-36c-3 0-5-2-5-5z" fill={url('body')} />
          <rect className="dl-bot__joint" x="110" y="331" width="42" height="5" rx="2.5" opacity=".75" />
        </g>
        <g className="dl-bot__leg dl-bot__leg--r">
          <rect x="156" y="262" width="26" height="54" rx="13" fill={url('body')} />
          <rect className="dl-bot__joint" x="156" y="284" width="26" height="6" rx="3" />
          <path d="M146 330c0-12 10-20 23-20s23 8 23 20v4c0 3-2 5-5 5h-36c-3 0-5-2-5-5z" fill={url('body')} />
          <rect className="dl-bot__joint" x="148" y="331" width="42" height="5" rx="2.5" opacity=".75" />
        </g>

        <g className="dl-bot__torso">
          <rect x="100" y="176" width="100" height="98" rx="44" fill={url('body')} />
          <path className="dl-bot__shine" d="M112 196c10-12 28-16 44-14" strokeOpacity=".7" strokeWidth="5" />
          <rect className="dl-bot__joint" x="104" y="248" width="92" height="7" rx="3.5" opacity=".8" />
          <rect className="dl-bot__chest" x="135" y="214" width="30" height="8" rx="4" filter={url('glow')} />
        </g>

        <g className="dl-bot__arm dl-bot__arm--l">
          <g transform="rotate(14 98 198)">
            <rect x="87" y="200" width="22" height="44" rx="11" fill={url('body')} />
            <rect className="dl-bot__joint" x="87" y="222" width="22" height="5" rx="2.5" />
            <circle cx="98" cy="252" r="11" fill={url('body')} />
          </g>
          <circle cx="98" cy="198" r="15" fill={url('body')} />
        </g>
        <g className="dl-bot__arm dl-bot__arm--r">
          <g transform="rotate(-14 202 198)">
            <rect x="191" y="200" width="22" height="44" rx="11" fill={url('body')} />
            <rect className="dl-bot__joint" x="191" y="222" width="22" height="5" rx="2.5" />
            <circle cx="202" cy="252" r="11" fill={url('body')} />
          </g>
          <circle cx="202" cy="198" r="15" fill={url('body')} />
        </g>

        <rect className="dl-bot__joint" x="134" y="166" width="32" height="18" rx="7" />

        <RobotHeadArt uid={uid} gaze={gaze} />
      </g></g>
    </svg>
  )

  const link = (n: number) => `${uid}-p${n}`
  return (
    <div className={`dl-ill${bare ? ' dl-ill--sm' : ''}`} data-state={shown}>
      <div className="dl-ill__stage">
        {!bare && (
          <>
            <div className="dl-ill__aura" aria-hidden="true" />
            <svg className="dl-ill__net" viewBox="0 0 560 460" aria-hidden="true" focusable="false">
              <g className="dl-ill__o1"><ellipse cx="280" cy="210" rx="250" ry="150" /><circle className="dl-ill__sat" cx="530" cy="210" r="4" /></g>
              <g className="dl-ill__o2"><ellipse cx="280" cy="210" rx="200" ry="200" /><circle className="dl-ill__sat" cx="280" cy="10" r="3" /></g>
              <path id={link(1)} className="dl-ill__link" d="M140 95 Q210 110 240 150" />
              <path id={link(2)} className="dl-ill__link" d="M455 95 Q380 110 330 150" />
              <path id={link(3)} className="dl-ill__link" d="M150 340 Q205 320 235 270" />
              <path id={link(4)} className="dl-ill__link" d="M425 345 Q370 320 330 270" />
              {!reduced && [['2.6s', '0s'], ['3.1s', '-1s'], ['2.8s', '-2s'], ['3.4s', '-.5s']].map(([dur, begin], i) => (
                <circle key={i} className="dl-ill__pkt" r="3.2">
                  <animateMotion dur={dur} begin={begin} repeatCount="indefinite"><mpath href={`#${link(i + 1)}`} /></animateMotion>
                </circle>
              ))}
            </svg>
            <i className="dl-ill__spark" style={{ left: '30%', top: '12%' }} aria-hidden="true" />
            <i className="dl-ill__spark" style={{ left: '72%', top: '46%', animationDelay: '-1.4s' }} aria-hidden="true" />
            <i className="dl-ill__spark" style={{ left: '22%', top: '58%', animationDelay: '-2.6s' }} aria-hidden="true" />
            <i className="dl-ill__spark" style={{ left: '64%', top: '4%', animationDelay: '-3.2s' }} aria-hidden="true" />

            <div className="dl-ill__card dl-ill__c-bars" aria-hidden="true">
              <div className="dl-ill__ln" style={{ width: '56%' }} />
              <div className="dl-ill__bars">
                {[44, 66, 52, 92, 60].map((h, i) => <i key={i} className={i === 3 ? 'is-accent' : undefined} style={{ height: `${h}%` }} />)}
              </div>
            </div>
            <div className="dl-ill__card dl-ill__c-donut" aria-hidden="true">
              <svg viewBox="0 0 64 64">
                <circle className="dl-ill__ring" cx="32" cy="32" r="24" />
                <circle className="dl-ill__ring is-accent" cx="32" cy="32" r="24" strokeDasharray="57 151" transform="rotate(-90 32 32)" />
                <circle className="dl-ill__ring is-accent is-more" cx="32" cy="32" r="24" strokeDasharray="80 151" transform="rotate(-90 32 32)" />
              </svg>
            </div>
            <div className="dl-ill__card dl-ill__c-chat" aria-hidden="true">
              <div className="dl-ill__ln" style={{ width: '88%' }} /><div className="dl-ill__ln" style={{ width: '62%' }} />
              <div className="dl-ill__ln is-soft" style={{ width: '74%' }} />
            </div>
            <div className="dl-ill__card dl-ill__c-table" aria-hidden="true">
              {[0, 1, 2, 3].map(r => (
                <div key={r} className={`dl-ill__tr${r ? ` is-r${r}` : ''}`}>
                  <div className="dl-ill__ln" /><div className={`dl-ill__ln${r === 1 ? ' is-accent' : ''}`} /><div className="dl-ill__ln" />
                </div>
              ))}
            </div>
          </>
        )}

        <span className="dl-ill__zz" aria-hidden="true" /><span className="dl-ill__zz is-z2" aria-hidden="true" /><span className="dl-ill__zz is-z3" aria-hidden="true" />
        <div className="dl-ill__fx" ref={fx} aria-hidden="true" />

        {reduced ? (
          <div className="dl-bot" data-state={shown} aria-hidden="true" ref={el => { robot.current = el }}>{drawing}</div>
        ) : (
          <button type="button" className="dl-bot" data-state={shown} aria-label={t('ask2.robot.label')}
            ref={el => { robot.current = el }} onClick={press}
            onPointerEnter={() => hover(true)} onPointerLeave={() => hover(false)}>
            {drawing}
          </button>
        )}
      </div>
    </div>
  )
}
