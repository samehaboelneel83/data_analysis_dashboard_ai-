import { forwardRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2,
  ArrowRight, ArrowUp, ArrowUpRight, Calendar, Check, Clock, Database, History, LayoutDashboard, Plug,
  Plus, RefreshCw, Sparkles, TriangleAlert, Upload, type LucideIcon,
} from 'lucide-react'
import AiMascot from '../../components/ai/AiMascot'
import { useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { useDirection } from '../../contexts/DirectionContext'
import Thumb from './Thumb'
import type { Widget } from '../../types/report'

/** Fills `{who}` / `{name}` slots of a translated sentence with elements, so
 *  the bold names keep their own direction inside either language. */
export function fill(template: string, parts: Record<string, ReactNode>): ReactNode[] {
  return template.split(/(\{\w+\})/).map((s, i) => {
    const m = /^\{(\w+)\}$/.exec(s)
    return m && m[1] in parts ? <span key={i}>{parts[m[1]]}</span> : <span key={i}>{s}</span>
  })
}

export const Sk = ({ w, h, r, style }: { w: string; h: number; r?: number; style?: React.CSSProperties }) =>
  <span className="sk" style={{ width: w, height: h, borderRadius: r, ...style }} />

export function SecHead({ id, title, count, all }: { id: string; title: string; count?: number; all?: string }) {
  const t = useT()
  return (
    <div className="hm-sechd">
      <h2 id={id}>{title}</h2>
      {count != null && <span className="hm-cnt">{localDigits(String(count))}</span>}
      <span className="hm-sp" />
      {all && <Link className="hm-all" to={all}>{t('common.viewAll')}<ArrowRight size={14} aria-hidden /></Link>}
    </div>
  )
}

export function Empty({ icon: Icon, title, text, actions, small }: {
  icon: LucideIcon; title: string; text: string; actions?: ReactNode; small?: boolean
}) {
  return (
    <div className={`hm-empty${small ? ' sm' : ''}`}>
      <span className="ei" aria-hidden><Icon size={small ? 18 : 20} /></span>
      <b>{title}</b>
      <p>{text}</p>
      {actions && <div className="acts">{actions}</div>}
    </div>
  )
}

/** One section's own failure: the rest of Home keeps working. */
export function SecError({ text, onRetry }: { text: string; onRetry: () => void }) {
  const t = useT()
  return (
    <div className="hm-secerr" role="alert">
      <TriangleAlert size={16} aria-hidden />
      <span>{text}</span>
      <span className="hm-sp" />
      <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
        <RefreshCw size={13} aria-hidden />{t('hm.retry')}
      </button>
    </div>
  )
}

// ── Hero ──────────────────────────────────────────────────────────────────

export interface HeroChips { datasetId: number; datasetName: string; questions: string[] }

export const Hero = forwardRef<HTMLInputElement, {
  name: string
  firstRun: boolean
  /** No data to ask about: the box is shown, inert, saying why. */
  noData: boolean
  offline: boolean
  loading: boolean
  chips: HeroChips | null
}>(function Hero({ name, firstRun, noData, offline, loading, chips }, ref) {
  const t = useT()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  // The chip on its way to Ask AI (QA2 B8): that page loads on demand, and
  // until it does the click must show it landed.
  const [going, setGoing] = useState<string | null>(null)
  const hr = new Date().getHours()
  const greeting = firstRun ? t('hm.welcome')
    : t(hr < 12 ? 'hm.morning' : hr < 18 ? 'hm.afternoon' : 'hm.evening')
  const { language } = useDirection()
  const lang = language === 'ar' ? 'ar' : 'en-US'
  const date = new Date().toLocaleDateString(lang, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  const locked = noData || offline
  const ask = (e: React.FormEvent) => {
    e.preventDefault()
    const text = q.trim()
    if (!text || locked) return
    navigate(`/ask?q=${encodeURIComponent(text)}`)
  }
  return (
    <section className="hm-hero" aria-labelledby="hm-h1">
      <div className="hm-date"><Calendar size={14} aria-hidden /><time>{date}</time></div>
      <h1 id="hm-h1">{fill(t('hm.greet', { greeting: '{greeting}', name: '{name}' }), { greeting, name: <bdi>{name}</bdi> })}</h1>
      <p className="sub">{t(firstRun ? 'hm.subFirst' : 'hm.sub')}</p>
      <form className={`hm-ask${locked ? ' off' : ''}`} role="search" aria-label={t('nav.askAi')} onSubmit={ask}>
        <span className={`hm-av${offline ? ' off' : ''}`}><AiMascot size={26} alive={!locked} /></span>
        <label className="dl-sr-only" htmlFor="hm-q">{t('hm.askLabel')}</label>
        <input id="hm-q" ref={ref} type="text" autoComplete="off" value={q} onChange={e => setQ(e.target.value)}
          dir="auto" disabled={locked}
          placeholder={t(noData ? 'hm.askNoData' : offline ? 'hm.askOffline' : 'hm.askLabel')} />
        <kbd>Enter</kbd>
        <button className="hm-send" type="submit" aria-label={t('nav.askAi')} title={t('nav.askAi')} disabled={locked || !q.trim()}>
          <ArrowUp size={18} strokeWidth={2.2} aria-hidden />
        </button>
      </form>
      {offline && !noData && <p className="hm-offline" role="status">{t('off.composer')}</p>}
      {loading ? (
        <div className="hm-chips">{[190, 160, 230, 210].map(w => <Sk key={w} w={`${w}px`} h={32} r={999} style={{ flex: 'none' }} />)}</div>
      ) : chips && !locked && (
        <div className="hm-chips" role="group" aria-label={t('hm.chipsAria', { name: chips.datasetName })}>
          <span className="hm-chips__about">{t('hm.chipsAbout')} <bdi>{chips.datasetName}</bdi></span>
          {chips.questions.map(c => (
            <button key={c} type="button" className="hm-chip" aria-busy={going === c || undefined}
              disabled={going != null && going !== c}
              onClick={() => { if (going) return; setGoing(c); navigate(`/ask?dataset=${chips.datasetId}&q=${encodeURIComponent(c)}`) }}>
              {going === c ? <Loader2 size={14} className="dl-spin" aria-hidden /> : <Sparkles size={14} aria-hidden />}{c}
            </button>
          ))}
        </div>
      )}
    </section>
  )
})

// ── Stat tiles ────────────────────────────────────────────────────────────

export interface Tile {
  key: string
  icon: LucideIcon
  label: string
  value: string
  /** A time rather than a count: drawn smaller. */
  textual?: boolean
  sub: string
  tone?: 'ok' | 'warn' | 'err'
  to: string
  onRetry?: () => void
}

export function Stats({ tiles, loading }: { tiles: Tile[]; loading: boolean }) {
  const t = useT()
  return (
    <section className="hm-stats" aria-label={t('hm.glance')}>
      {loading ? [0, 1, 2, 3].map(i => (
        <div key={i} className="hm-st"><Sk w="55%" h={10} /><Sk w="40%" h={22} style={{ marginTop: 8 }} /><Sk w="70%" h={10} style={{ marginTop: 8 }} /></div>
      )) : tiles.map(x => (
        <div key={x.key} className="hm-st" data-testid={`hm-tile-${x.key}`}>
          <Link className="hm-st__link" to={x.to} aria-label={`${x.label}: ${x.value}. ${x.sub}`} />
          <span className="l"><x.icon size={14} aria-hidden />{x.label}</span>
          <span className={`v${x.textual ? ' t' : ''}`}>{x.value}</span>
          <span className="s">
            {x.tone && <span className={`hm-dot ${x.tone}`} aria-hidden />}
            <span title={x.sub}>{x.sub}</span>
            {x.onRetry && <button type="button" className="hm-st__retry" onClick={x.onRetry}>{t('hm.retry')}</button>}
          </span>
          <ArrowUpRight size={14} className="go" aria-hidden />
        </div>
      ))}
    </section>
  )
}

// ── Quick actions ─────────────────────────────────────────────────────────

export function Quick({ onAsk, askTo }: { onAsk?: () => void; askTo?: string }) {
  const t = useT()
  const items: { k: string; icon: ReactNode; title: MessageKey; sub: MessageKey; to?: string; onClick?: () => void }[] = [
    { k: 'a', icon: <Plus size={19} />, title: 'hm.qa.newDash', sub: 'hm.qa.newDashSub', to: '/reports?new=1' },
    { k: 'u', icon: <Upload size={19} />, title: 'hm.qa.upload', sub: 'hm.qa.uploadSub', to: '/upload' },
    { k: 'c', icon: <Plug size={19} />, title: 'hm.qa.connect', sub: 'hm.qa.connectSub', to: '/connections' },
    { k: 'i', icon: <span className="hm-av"><AiMascot size={26} /></span>, title: 'nav.askAi', sub: 'hm.qa.askSub', to: askTo, onClick: onAsk },
  ]
  return (
    <nav className="hm-quick" aria-label={t('hm.quick')}>
      {items.map(i => {
        const body = <>
          <span className="ic" aria-hidden>{i.icon}</span>
          <span className="tx"><b>{t(i.title)}</b><small>{t(i.sub)}</small></span>
          <ArrowRight size={16} className="ar" aria-hidden />
        </>
        return i.to
          ? <Link key={i.k} to={i.to} className={`hm-qa q-${i.k}`}>{body}</Link>
          : <button key={i.k} type="button" className={`hm-qa q-${i.k}`} onClick={i.onClick}>{body}</button>
      })}
    </nav>
  )
}

// ── Continue where you left off ───────────────────────────────────────────

export interface ContinueItem { id: number; name: string; when: string | null; widgets: Widget[] | null }

export function Continue({ items, loading, error, onRetry, onOpen }: {
  items: ContinueItem[]; loading: boolean; error: boolean; onRetry: () => void; onOpen: () => void
}) {
  const t = useT()
  let body: ReactNode
  if (loading) {
    body = <div className="hm-cont">{[0, 1, 2, 3].map(i => (
      <div key={i} className="hm-cc"><span className="sk" style={{ aspectRatio: '16/9', borderRadius: 0 }} />
        <div className="hm-cb"><Sk w="85%" h={13} /><Sk w="50%" h={10} style={{ marginTop: 6 }} /></div></div>
    ))}</div>
  } else if (error) {
    body = <SecError text={t('hm.err.recent')} onRetry={onRetry} />
  } else if (!items.length) {
    body = <Empty icon={History} title={t('hm.cont.empty')} text={t('hm.cont.emptyText')} />
  } else {
    body = <div className="hm-cont" data-testid="home-recents">{items.map(c => (
      <article key={c.id} className="hm-cc">
        <div className="hm-th-w">
          <Thumb widgets={c.widgets} />
          <span className="hm-type"><LayoutDashboard size={12} aria-hidden />{t('hm.type.dashboard')}</span>
        </div>
        <div className="hm-cb">
          <Link className="hm-link hm-cn" to={`/reports/${c.id}`} title={c.name} data-testid={`home-recent-${c.id}`}
            onClick={e => { if (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) onOpen() }}>
            <bdi>{c.name}</bdi>
          </Link>
          {c.when && <div className="hm-cm"><Clock size={13} aria-hidden />{t('home.opened', { when: c.when })}</div>}
        </div>
      </article>
    ))}</div>
  }
  return <section className="hm-sec" aria-labelledby="hm-cont"><SecHead id="hm-cont" title={t('hm.cont.title')} />{body}</section>
}

// ── First run ─────────────────────────────────────────────────────────────

export function Onboarding({ done, onAsk }: { done: [boolean, boolean, boolean]; onAsk: () => void }) {
  const t = useT()
  const n = done.filter(Boolean).length
  const cur = done.indexOf(false)
  const steps: { title: MessageKey; text: MessageKey; actions: ReactNode }[] = [
    { title: 'hm.onb.connect', text: 'hm.onb.connectText', actions: <>
      <Link className="btn btn-primary btn-sm" to="/upload"><Upload size={14} aria-hidden />{t('hm.qa.upload')}</Link>
      <Link className="btn btn-ghost btn-sm" to="/connections"><Plug size={14} aria-hidden />{t('hm.qa.connect')}</Link>
    </> },
    { title: 'hm.onb.build', text: 'hm.onb.buildText', actions:
      <Link className="btn btn-primary btn-sm" to="/reports?new=1"><Plus size={14} aria-hidden />{t('hm.qa.newDash')}</Link> },
    { title: 'nav.askAi', text: 'hm.onb.askText', actions:
      <button type="button" className="btn btn-primary btn-sm" onClick={onAsk}><Sparkles size={14} aria-hidden />{t('nav.askAi')}</button> },
  ]
  return (
    <section className="hm-onb" aria-labelledby="hm-onb" data-testid="home-onboarding">
      <div>
        <div className="hm-eyb">{t('hm.onb.eyebrow')}</div>
        <h2 id="hm-onb">{t(n >= 3 ? 'hm.onb.allSet' : 'hm.onb.title')}</h2>
        <div className="hm-prog">
          <span className="tr" role="progressbar" aria-valuemin={0} aria-valuemax={3} aria-valuenow={n} aria-label={t('hm.onb.progress')}>
            <i style={{ width: `${(n / 3) * 100}%` }} />
          </span>
          <span>{t('hm.onb.count', { n: localDigits(String(n)), of: localDigits('3') })}</span>
        </div>
        <ol className="hm-steps">
          {steps.map((s, i) => {
            const state = done[i] ? 'done' : i === cur ? 'cur' : ''
            return (
              <li key={s.title} className={`hm-step ${state}`} aria-current={i === cur ? 'step' : undefined}>
                <span className="hm-sn">{done[i] ? <Check size={15} strokeWidth={2.4} aria-hidden /> : localDigits(String(i + 1))}</span>
                <div className="tx"><b>{t(s.title)}</b><p>{t(s.text)}</p></div>
                {i === cur ? <div className="hm-sa">{s.actions}</div> : done[i] ? <span className="hm-ok">{t('hm.onb.done')}</span> : null}
              </li>
            )
          })}
        </ol>
      </div>
      <div className="hm-ill" aria-hidden>
        <div className="hm-glow" />
        <svg className="hm-lines" viewBox="0 0 400 300" preserveAspectRatio="none" fill="none">
          <g stroke="var(--mc-border-strong)" strokeWidth="1.6" strokeDasharray="1 6" strokeLinecap="round">
            <path d="M130 80Q160 100 172 124" /><path d="M290 90Q262 104 236 126" />
            <path d="M110 240Q150 226 170 188" /><path d="M300 230Q262 220 232 186" />
          </g>
        </svg>
        <div className="hm-fc f1">
          <div className="k"><i style={{ width: '55%' }} /></div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 5, height: 46, marginTop: 10 }}>
            {[44, 70, 54, 96, 62].map((h, i) => <i key={i} style={{ flex: 1, height: `${h}%`, borderRadius: '3px 3px 1px 1px',
              background: i === 3 ? 'var(--accent)' : 'var(--mc-border-strong)' }} />)}
          </div>
        </div>
        <div className="hm-fc f2">{[0, 1, 2].map(i => <div key={i}><Database size={13} /><i /></div>)}</div>
        <div className="hm-fc f3"><i /><i style={{ opacity: .6 }} /><i style={{ opacity: .3 }} /></div>
        <div className="hm-fc f4">
          <svg viewBox="0 0 40 40" width="56" height="56">
            <circle cx="20" cy="20" r="13" fill="none" stroke="var(--surface2)" strokeWidth="7" />
            <circle cx="20" cy="20" r="13" fill="none" stroke="var(--accent)" strokeWidth="7" strokeDasharray="30 82" transform="rotate(-90 20 20)" />
          </svg>
        </div>
        <span className="hm-av xl"><AiMascot size={80} alive /></span>
      </div>
    </section>
  )
}
