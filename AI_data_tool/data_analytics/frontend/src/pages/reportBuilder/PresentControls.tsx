import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Keyboard, Pause, Timer, X } from 'lucide-react'
import AiMascot from '../../components/ai/AiMascot'
import { useDirection } from '../../contexts/DirectionContext'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/**
 * Present (redesign 7d): the dashboard full screen, with the header gone
 * (the owner allowed it, as long as Esc and these controls still exit).
 *
 * Pages advance on their own as v1's kiosk did -- auto-play is on, and can be
 * paused here -- now every 15 s, with a progress line. Arrow keys, Space and
 * Page Up / Down move between pages (mirrored in Arabic); Esc closes the AI
 * panel if it is open, then exits. v1 exited on ANY key, which made the arrow
 * keys unusable. After 2.5 s without the mouse or a key, the title and the
 * controls fade until the reader moves again.
 */

export const AUTO_MS = 15000
const IDLE_MS = 2500

export default function PresentControls({ title, pages, activeId, onGo, onExit, onAsk, aiOpen, onCloseAi }: {
  title: string
  pages: { id: number; name: string }[]
  activeId: number | null
  onGo: (id: number) => void
  onExit: () => void
  onAsk: () => void
  aiOpen: boolean
  onCloseAi: () => void
}) {
  const t = useT()
  const { rtl } = useDirection()
  const [auto, setAuto] = useState(true)
  const [idle, setIdle] = useState(false)
  const i = Math.max(0, pages.findIndex(p => p.id === activeId))
  const go = (n: number) => { if (n >= 0 && n < pages.length) onGo(pages[n].id) }

  // Latest values for the listeners, without re-binding them every render.
  const live = useRef({ i, go, onExit, aiOpen, onCloseAi, rtl })
  live.current = { i, go, onExit, aiOpen, onCloseAi, rtl }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable) return
      const L = live.current
      const next = L.rtl ? 'ArrowLeft' : 'ArrowRight'
      const prev = L.rtl ? 'ArrowRight' : 'ArrowLeft'
      if (e.key === 'Escape') { e.preventDefault(); if (L.aiOpen) L.onCloseAi(); else L.onExit() }
      else if (e.key === next || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); L.go(L.i + 1) }
      else if (e.key === prev || e.key === 'PageUp') { e.preventDefault(); L.go(L.i - 1) }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // Auto-play: the next page, wrapping round, as v1's kiosk did.
  useEffect(() => {
    if (!auto || aiOpen || pages.length < 2) return
    const id = setTimeout(() => live.current.go((live.current.i + 1) % pages.length), AUTO_MS)
    return () => clearTimeout(id)
  }, [auto, aiOpen, pages.length, activeId])

  useEffect(() => {
    let timer = setTimeout(() => setIdle(true), IDLE_MS)
    const wake = () => { setIdle(false); clearTimeout(timer); timer = setTimeout(() => setIdle(true), IDLE_MS) }
    const evs = ['mousemove', 'keydown', 'pointerdown'] as const
    evs.forEach(ev => document.addEventListener(ev, wake))
    return () => { clearTimeout(timer); evs.forEach(ev => document.removeEventListener(ev, wake)) }
  }, [])
  // The idle class lives on <html>, so the fade reaches whatever sits outside
  // this component without passing state around.
  useEffect(() => {
    document.documentElement.classList.toggle('dl-pr-idle', idle && !aiOpen)
    return () => document.documentElement.classList.remove('dl-pr-idle')
  }, [idle, aiOpen])

  const page = pages[i]
  return (
    <>
      <div className="dl-pr-ttl"><b><bdi>{title}</bdi></b>{page && <><span className="sep" aria-hidden /><bdi>{page.name}</bdi></>}</div>
      <div className="dl-pr-kb" aria-hidden>
        <Keyboard size={14} />
        <span><kbd>←</kbd> <kbd>→</kbd> {t('vw.pr.navigate')}</span>
        <span><kbd>Esc</kbd> {t('vw.pr.toExit')}</span>
      </div>
      <nav className="dl-pr-ctl" aria-label={t('vw.pr.aria')} data-testid="present-controls">
        <button type="button" className="ib" onClick={() => go(i - 1)} disabled={i <= 0} aria-label={t('vw.pr.prev')} title={t('vw.pr.prev')}>
          <ChevronLeft size={18} className="flip" aria-hidden />
        </button>
        <span className="pn" dir="ltr">{localDigits(`${i + 1} / ${pages.length}`)}</span>
        <button type="button" className="ib" onClick={() => go(i + 1)} disabled={i >= pages.length - 1} aria-label={t('vw.pr.next')} title={t('vw.pr.next')}>
          <ChevronRight size={18} className="flip" aria-hidden />
        </button>
        {pages.length > 1 && (
          <div className="dl-pr-dots">
            {pages.map((p, n) => (
              <button key={p.id} type="button" aria-current={n === i} onClick={() => go(n)} aria-label={t('vw.pr.page', { n: localDigits(String(n + 1)), name: p.name })} />
            ))}
          </div>
        )}
        <span className="vr" aria-hidden />
        {pages.length > 1 && (
          <button type="button" className="dl-pr-btn" aria-pressed={auto} onClick={() => setAuto(a => !a)}>
            {auto ? <Pause size={15} aria-hidden /> : <Timer size={15} aria-hidden />}{t('vw.pr.auto')} <span dir="ltr">{localDigits('15s')}</span>
          </button>
        )}
        <button type="button" className="dl-pr-btn" onClick={onAsk}>
          <span className="dl-vw-av" aria-hidden><AiMascot size={16} /></span>{t('nav.askAi')}
        </button>
        <span className="vr" aria-hidden />
        <button type="button" className="dl-pr-btn exit" onClick={onExit}><X size={15} aria-hidden />{t('vw.pr.exit')}<kbd>Esc</kbd></button>
      </nav>
      {auto && !aiOpen && pages.length > 1 && (
        <div className="dl-pr-prog" aria-hidden><i key={activeId ?? 0} style={{ animationDuration: `${AUTO_MS}ms` }} /></div>
      )}
    </>
  )
}
