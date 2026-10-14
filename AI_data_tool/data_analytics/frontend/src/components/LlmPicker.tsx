import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Check, ChevronDown, RefreshCw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'
import { MOBILE_QUERY, useMediaQuery } from '../hooks/useMediaQuery'
import {
  getLlmChoice, llmApi, LLM_CHOICE_EVENT, LLM_USED_EVENT, setLlmChoice,
  type LlmEndpoint, type LlmEndpointsOut, type LlmUsedStep,
} from '../services/api'

/**
 * The AI model light and picker in the top bar.
 *
 * The light says, before anyone types a question, whether the model their AI
 * requests will go to is answering: green up, red not reachable, grey not
 * checked yet or AI turned off. The menu lists Auto and every endpoint the
 * platform admin set up, each with its own light, so when the default goes
 * red a person can move to one that is green (or to Auto, which does that by
 * itself). The pick is this browser's: `setLlmChoice` stores it and the axios
 * instance sends it with every request (services/api.ts).
 */

const POLL_MS = 30_000
/** How long the button stays highlighted after Auto switched model. */
const FLASH_MS = 2500

/** The model that carried a request: its last HEAVY step (the SQL, the plan:
 *  what the answer depends on), else its last step. */
export function mainStep(steps: LlmUsedStep[]): LlmUsedStep | undefined {
  return [...steps].reverse().find(s => s.weight === 'heavy') ?? steps[steps.length - 1]
}

export type Light = 'up' | 'down' | 'unknown' | 'off'

export function endpointLight(ep: Pick<LlmEndpoint, 'enabled' | 'status'> | undefined, aiOn = true): Light {
  if (!aiOn || !ep || !ep.enabled) return 'off'
  if (!ep.status) return 'unknown'
  return ep.status.ok ? 'up' : 'down'
}

/** What the person's requests use: their pick when it still exists, else the default. */
export function effectiveChoice(data: LlmEndpointsOut, picked: string | null): string {
  if (picked === 'auto') return 'auto'
  if (picked && data.endpoints.some(e => e.id === picked && e.enabled)) return picked
  return data.default
}

export function choiceLight(data: LlmEndpointsOut, choice: string): Light {
  if (!data.llm_enabled) return 'off'
  if (choice === 'auto') {
    if (data.auto_pick) return 'up'
    return data.endpoints.some(e => e.enabled && !e.status) ? 'unknown' : 'down'
  }
  return endpointLight(data.endpoints.find(e => e.id === choice))
}

const LIGHT_COLOR: Record<Light, string> = {
  up: 'var(--success)', down: 'var(--danger)', unknown: 'var(--warning, #d4a106)', off: 'var(--muted)',
}

export function Led({ light, size = 9 }: { light: Light; size?: number }) {
  const color = LIGHT_COLOR[light]
  return (
    <span aria-hidden data-light={light} className={`dl-led dl-led--${light}`}
      style={{ width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'inline-block',
        background: color,
        boxShadow: light === 'up' || light === 'down'
          ? `0 0 0 2px color-mix(in srgb, ${color} 22%, transparent), 0 0 6px ${color}` : 'none' }} />
  )
}

export default function LlmPicker() {
  const t = useT()
  const { user } = useAuth()
  const compact = useMediaQuery(MOBILE_QUERY)
  const [data, setData] = useState<LlmEndpointsOut | null>(null)
  const [picked, setPicked] = useState<string | null>(() => getLlmChoice())
  const [open, setOpen] = useState(false)
  const [checking, setChecking] = useState(false)
  /** The steps of the most recent request that used a model, as the server
   *  reported them (X-LLM-Used), or this person's last use after a reload. */
  const [used, setUsed] = useState<LlmUsedStep[]>([])
  const [flash, setFlash] = useState(false)
  const lastMain = useRef<string | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async (refresh = false) => {
    if (refresh) setChecking(true)
    try {
      const out = await llmApi.endpoints(refresh)
      setData(out)
      const latest = out.last_used?.[out.last_used.length - 1]
      setUsed(cur => (cur.length || !latest ? cur : [{ id: latest.id, weight: latest.weight }]))
      if (latest && lastMain.current === null) lastMain.current = latest.id
      // A pick of an endpoint the admin has since removed or turned off would
      // otherwise be sent forever and silently ignored by the server.
      const mine = getLlmChoice()
      if (mine && mine !== 'auto' && !out.endpoints.some(e => e.id === mine && e.enabled)) {
        setLlmChoice(null)
      }
    } catch { /* the light stays as it was; the next poll tries again */ }
    finally { if (refresh) setChecking(false) }
  }, [])

  useEffect(() => {
    if (!user) return
    void load()
    const id = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load() }, POLL_MS)
    const onFocus = () => void load()
    const onChoice = (e: Event) => setPicked((e as CustomEvent<string | null>).detail ?? null)
    const onUsed = (e: Event) => setUsed((e as CustomEvent<LlmUsedStep[]>).detail ?? [])
    window.addEventListener('focus', onFocus)
    window.addEventListener(LLM_CHOICE_EVENT, onChoice)
    window.addEventListener(LLM_USED_EVENT, onUsed)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('focus', onFocus)
      window.removeEventListener(LLM_CHOICE_EVENT, onChoice)
      window.removeEventListener(LLM_USED_EVENT, onUsed)
    }
  }, [user, load])

  // Highlight the button when Auto moved to a different model than last time.
  const main = mainStep(used)?.id ?? null
  useEffect(() => {
    if (!main) return
    const switched = lastMain.current !== null && lastMain.current !== main
    lastMain.current = main
    if (!switched) return
    setFlash(true)
    const id = window.setTimeout(() => setFlash(false), FLASH_MS)
    return () => window.clearTimeout(id)
  }, [main, used])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!user || !data) return null

  const choice = effectiveChoice(data, picked)
  const byId = (id: string | null | undefined) => data.endpoints.find(e => e.id === id)
  const autoEp = byId(data.auto_pick)
  const current = byId(choice)
  // On Auto the button names the model that REALLY answered the last request
  // (reported by the server), not a guess: "Auto → Qwen 3.8 27B".
  const usedEp = choice === 'auto' ? byId(main) : undefined
  const light = usedEp ? endpointLight(usedEp, data.llm_enabled) : choiceLight(data, choice)
  const name = choice === 'auto'
    ? (usedEp ? `${t('llm.auto')} → ${usedEp.name}` : `${t('llm.auto')}${autoEp ? ` · ${autoEp.name}` : ''}`)
    : current?.name ?? choice
  const weightLabel = (w: string) => (w === 'heavy' ? t('llm.w.heavy') : w === 'light' ? t('llm.w.light') : t('llm.w.normal'))
  const trail = used.map(u => `${byId(u.id)?.name ?? u.id} (${weightLabel(u.weight)})`)
  // Consecutive steps on the same model read as one: "9B (light) → 27B (heavy)".
  const trailText = trail.filter((x, i) => x !== trail[i - 1]).join(' → ')
  const state = !data.llm_enabled ? t('llm.off')
    : light === 'up' ? t('llm.up') : light === 'down' ? t('llm.down') : t('llm.unknown')

  const pick = (id: string) => { setLlmChoice(id); setPicked(id); setOpen(false) }

  const row = (id: string, label: string, sub: string, l: Light, opts: { disabled?: boolean; tag?: string; title?: string } = {}) => {
    const selected = id === choice
    return (
      <button key={id} type="button" role="menuitemradio" aria-checked={selected} disabled={opts.disabled}
        onClick={() => pick(id)} title={opts.title}
        style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', border: 'none',
          background: selected ? 'var(--accent-soft)' : 'none', cursor: opts.disabled ? 'not-allowed' : 'pointer',
          opacity: opts.disabled ? 0.55 : 1, textAlign: 'start', padding: '7px 10px', borderRadius: 7,
          fontFamily: 'var(--sans)', color: 'var(--text)' }}>
        <span aria-hidden style={{ width: 13, display: 'inline-flex', flexShrink: 0, color: 'var(--accent)' }}>
          {selected && <Check size={13} />}
        </span>
        <Led light={l} />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
            fontWeight: selected ? 650 : 500, color: selected ? 'var(--accent)' : 'var(--text)' }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
            {opts.tag && (
              <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--muted)', border: '1px solid var(--border)',
                borderRadius: 4, padding: '0 4px', textTransform: 'uppercase' }}>{opts.tag}</span>
            )}
          </span>
          <span style={{ display: 'block', fontSize: 11, color: l === 'down' ? 'var(--danger)' : 'var(--muted)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</span>
        </span>
      </button>
    )
  }

  const epSub = (ep: LlmEndpoint) => {
    const l = endpointLight(ep, data.llm_enabled)
    if (l === 'off') return `${ep.model} · ${t('llm.disabled')}`
    if (l === 'down') return ep.status?.error ?? t('llm.down')
    if (l === 'up') {
      return [ep.model, ep.context ? t('llm.ctx', { k: Math.round(ep.context / 1024) }) : null,
        ep.status?.latency_ms != null ? t('llm.ms', { ms: ep.status.latency_ms }) : null].filter(Boolean).join(' · ')
    }
    return `${ep.model} · ${t('llm.unknown')}`
  }

  return (
    <div ref={rootRef} style={{ position: 'relative' }} data-testid="llm-picker">
      <button type="button" onClick={() => setOpen(o => !o)}
        aria-label={t('llm.aria', { name, state })}
        title={`${name}: ${state}${trailText ? `\n${t('llm.lastRequest', { steps: trailText })}` : ''}`}
        aria-expanded={open} aria-haspopup="menu" data-switched={flash || undefined}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
          background: flash ? 'var(--accent-soft)' : 'none',
          border: `1px solid ${flash ? 'var(--accent)' : 'var(--border)'}`, cursor: 'pointer', padding: '4px 8px',
          borderRadius: 8, transition: 'background .3s, border-color .3s',
          color: open ? 'var(--accent)' : 'var(--muted)', fontFamily: 'var(--sans)', maxWidth: 260 }}>
        <Led light={light} />
        <Bot size={16} strokeWidth={1.9} aria-hidden />
        {!compact && (
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
        )}
        <ChevronDown size={12} aria-hidden />
      </button>

      {open && (
        <div role="menu" aria-label={t('llm.menu')}
          style={{ position: 'absolute', insetInlineEnd: 0, top: '115%', zIndex: 900, width: 300,
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
            boxShadow: '0 8px 24px rgb(15 23 42 / .12)', padding: 6 }}>
          {!data.llm_enabled && (
            <p role="status" style={{ fontSize: 12, color: 'var(--danger)', margin: '4px 10px 8px' }}>{t('llm.off')}</p>
          )}
          {/* 4.9: a business user saw a list of model names and had to ask
              what picking one would change. Said here, in plain words. */}
          <details data-testid="llm-explainer" style={{ margin: '2px 8px 6px', fontSize: 11.5, lineHeight: 1.5 }}>
            <summary style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600 }}>{t('llm.whatTitle')}</summary>
            <ul style={{ margin: '4px 0 0', paddingInlineStart: 16, color: 'var(--text)' }}>
              <li>{t('llm.whatUses')}</li>
              <li>{t('llm.whatTrade')}</li>
              <li>{t('llm.whatAuto')}</li>
              <li>{user.is_super_admin ? t('llm.whatDefaultAdmin') : t('llm.whatDefault')}</li>
            </ul>
          </details>
          {row('auto', t('llm.auto'),
            usedEp ? t('llm.autoUsed', { name: usedEp.name })
              : autoEp ? t('llm.autoUsing', { name: autoEp.name })
              : (choiceLight(data, 'auto') === 'unknown' ? t('llm.unknown') : t('llm.autoNone')),
            choiceLight(data, 'auto'),
            { tag: data.default === 'auto' ? t('llm.default') : undefined, title: t('llm.autoHint') })}
          {trailText && (
            <p data-testid="llm-last-request" style={{ fontSize: 11, color: 'var(--muted)', margin: '2px 10px 4px 32px',
              lineHeight: 1.45 }}>
              {t('llm.lastRequest', { steps: trailText })}
            </p>
          )}
          <div aria-hidden style={{ borderTop: '1px solid var(--border)', margin: '4px 6px' }} />
          {data.endpoints.map(ep => row(ep.id, ep.name, epSub(ep), endpointLight(ep, data.llm_enabled), {
            disabled: !ep.enabled, tag: ep.is_default ? t('llm.default') : undefined,
            title: ep.status?.error ?? undefined,
          }))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, borderTop: '1px solid var(--border)',
            marginTop: 6, padding: '6px 8px 2px' }}>
            <button type="button" className="btn btn-sm" disabled={checking} onClick={() => void load(true)}>
              <RefreshCw size={12} aria-hidden /> {checking ? t('llm.checking') : t('llm.refresh')}
            </button>
            <span style={{ flex: 1 }} />
            {user.is_super_admin && (
              <Link to="/platform/settings" onClick={() => setOpen(false)} style={{ fontSize: 12 }}>{t('llm.manage')}</Link>
            )}
          </div>
          <p style={{ fontSize: 10.5, color: 'var(--muted)', lineHeight: 1.45, margin: '6px 8px 2px' }}>
            {t('llm.pickHint')}
          </p>
        </div>
      )}
    </div>
  )
}
