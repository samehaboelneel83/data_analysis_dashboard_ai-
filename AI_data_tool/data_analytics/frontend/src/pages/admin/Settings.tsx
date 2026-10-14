import { useContext, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { RotateCcw, RefreshCw, Lock } from 'lucide-react'
import { AuthContext } from '../../contexts/AuthContext'
import { useT, en as EN, type MessageKey, type TranslateFn } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { isolate } from '../../i18n/pages/adminPlatform'
import { platformSettingsApi, type PlatformSetting, type PlatformSettingsOut } from '../../services/api'
import BasemapSettings from '../../components/admin/BasemapSettings'
import LlmEndpointsPanel from '../../components/admin/LlmEndpointsPanel'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'
import { formatDate } from '../../lib/dateFormat'

/**
 * Admin -> Settings: every setting in one place.
 *
 * "This organization" holds what an org admin sets for their own org: the map
 * tile server inline, and links to the other org pages. "Platform" holds the
 * install-wide settings (LLM, mail, limits, timeouts...), for platform admins:
 * a saved value overrides the environment variable and applies at once; Reset
 * puts the environment value back. Deploy-time settings are shown read-only,
 * and a secret's value never comes back from the server.
 */

type Draft = string | boolean

/**
 * 8-i18n: the platform catalog's words come from the server, in English. They
 * are translated here by category id / setting key; English shows exactly what
 * the server sent, and a key this client does not know keeps the server's text.
 * (Backend follow-up: the server should send keys/codes, not English prose.)
 */
function catalogText(t: TranslateFn, language: string, key: string, fallback: string): string {
  if (language === 'en' || !fallback) return fallback
  const k = `pg.adminPlatform.${key}`
  return k in EN ? t(k as MessageKey) : fallback
}
type Words = { label: (s: PlatformSetting) => string; help: (s: PlatformSetting) => string }
function useCatalogWords(): Words & { category: (id: string, fallback: string) => string } {
  const t = useT()
  const { language } = useDirection()
  return useMemo(() => ({
    label: (s: PlatformSetting) => catalogText(t, language, `set.${s.key}`, s.label),
    help: (s: PlatformSetting) => catalogText(t, language, `set.${s.key}.help`, s.help),
    category: (id: string, fallback: string) => catalogText(t, language, `cat.${id}`, fallback),
  }), [t, language])
}

/** A value that is a code, not words -- a URL, a model id, a host list, the
 *  JSON endpoint list (LLM_ENDPOINTS): read left to right, isolated, left-aligned,
 *  so it is not scrambled inside the Arabic page. */
const LTR_VALUE = { direction: 'ltr', unicodeBidi: 'isolate', textAlign: 'left' } as const

const OPEN_BY_DEFAULT = new Set(['ai', 'email', 'data', 'maps'])

const ORG_LINKS: { to: string; key: Parameters<ReturnType<typeof useT>>[0] }[] = [
  { to: '/admin/maps', key: 'nav.maps' },
  { to: '/admin/sso', key: 'nav.sso' },
  { to: '/admin/export-policy', key: 'nav.exportPolicy' },
  { to: '/admin/calendar', key: 'nav.calendar' },
  { to: '/admin/api-keys', key: 'nav.apiKeys' },
  { to: '/admin/custom-connectors', key: 'nav.customConnectors' },
]

function detail(e: unknown): string | undefined {
  return (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
}

function toValue(s: PlatformSetting, d: Draft, t: TranslateFn, label: string): string | number | boolean | { error: string } {
  if (s.type === 'bool') return Boolean(d)
  if (s.type === 'int' || s.type === 'float') {
    const text = String(d).trim()
    const n = s.type === 'int' ? Number.parseInt(text, 10) : Number.parseFloat(text)
    if (text === '' || !Number.isFinite(n) || (s.type === 'int' && !/^-?\d+$/.test(text))) {
      return { error: t(s.type === 'int' ? 'pg.adminPlatform.set.enterInt' : 'pg.adminPlatform.set.enterNum', { label }) }
    }
    return n
  }
  return String(d)
}

function SettingRow({ s, draft, onChange, onReset, busy, words }: {
  s: PlatformSetting; draft: Draft | undefined; onChange: (d: Draft) => void; onReset: () => void; busy: boolean; words: Words
}) {
  const t = useT()
  const { language } = useDirection()
  const label = words.label(s)
  const help = words.help(s)
  // Text settings hold codes (URLs, ids, host lists, JSON), never prose.
  const code = s.type === 'str' && !s.secret
  const id = `setting-${s.key}`
  const hintId = `${id}-hint`
  const shown: Draft = draft ?? (s.type === 'bool' ? Boolean(s.value) : s.value == null ? '' : String(s.value))
  const range = [s.bounds.ge ?? s.bounds.gt, s.bounds.le ?? s.bounds.lt]
  let input
  if (!s.editable) {
    input = (
      s.secret || s.value === '' || s.value == null
        ? <span id={id} className="dl-setting__readonly">
            {s.secret ? (s.is_set ? '••••••' : t('settings.secretUnset')) : '—'}
          </span>
        : <span id={id} className="dl-setting__readonly" dir={code ? 'ltr' : undefined} style={code ? LTR_VALUE : undefined}>
            {String(s.value)}
          </span>
    )
  } else if (s.type === 'bool') {
    input = <input id={id} type="checkbox" checked={Boolean(shown)} aria-describedby={hintId}
      onChange={e => onChange(e.target.checked)} />
  } else if (s.secret) {
    input = <input id={id} type="password" autoComplete="new-password" value={String(draft ?? '')}
      placeholder={s.is_set ? t('settings.secretSet') : t('settings.secretUnset')} aria-describedby={hintId}
      onChange={e => onChange(e.target.value)} className="dl-field__input" />
  } else {
    input = <input id={id} type="text" inputMode={s.type === 'str' ? undefined : 'decimal'} value={String(shown)}
      aria-describedby={hintId} onChange={e => onChange(e.target.value)} className="dl-field__input"
      dir={code ? 'ltr' : undefined} style={code ? LTR_VALUE : undefined} />
  }
  return (
    <div className="dl-setting" data-testid={`setting-${s.key}`}>
      <div className="dl-setting__head">
        <label htmlFor={id} className="dl-setting__label">{label}</label>
        {s.restart && <span className="dl-setting__badge" title={t('settings.restart')}><RefreshCw size={11} aria-hidden /> {t('settings.restart')}</span>}
        {!s.editable && <span className="dl-setting__badge"><Lock size={11} aria-hidden /> {t('settings.readOnly')}</span>}
        {s.editable && s.source === 'saved' && (
          <span className="dl-setting__badge dl-setting__badge--saved"
            title={s.updated_by ? (s.updated_at
              ? t('pg.adminPlatform.set.savedByAt', { who: s.updated_by, when: formatDate(s.updated_at) })
              : t('pg.adminPlatform.set.savedBy', { who: s.updated_by })) : undefined}>
            {t('settings.source.saved')}
          </span>
        )}
      </div>
      <div className="dl-setting__control">
        {input}
        {s.editable && s.source === 'saved' && (
          <button type="button" className="btn btn-sm" disabled={busy} onClick={onReset}
            aria-label={t('pg.adminPlatform.set.resetOf', { reset: t('settings.reset'), name: isolate(language, label) })}>
            <RotateCcw size={12} aria-hidden /> {t('settings.reset')}
          </button>
        )}
      </div>
      <p id={hintId} className="dl-setting__hint">
        {help}{help && ' '}
        {s.editable && !s.secret && s.source === 'saved' && s.default != null && s.default !== '' &&
          <span>{t('settings.environmentValue', { value: isolate(language, String(s.default)) })} </span>}
        {s.editable && (s.type === 'int' || s.type === 'float') && range.some(v => v != null) &&
          <span>{t('settings.range', { min: range[0] ?? '—', max: range[1] ?? '—' })}</span>}
      </p>
    </div>
  )
}

function PlatformSettings() {
  const t = useT()
  const { language } = useDirection()
  const words = useCatalogWords()
  const [data, setData] = useState<PlatformSettingsOut | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [testing, setTesting] = useState(false)

  const load = () => {
    setLoadError(null)
    platformSettingsApi.get().then(setData).catch(setLoadError)
  }
  useEffect(load, [])

  const byKey = useMemo(() => {
    const m: Record<string, PlatformSetting> = {}
    data?.categories.forEach(c => c.settings.forEach(s => { m[s.key] = s }))
    return m
  }, [data])

  const dirty = Object.keys(drafts)
  const apply = (out: PlatformSettingsOut, message: string) => {
    setData(out); setDrafts({})
    const restart = out.restart_required ?? []
    if (restart.length) toast(t('settings.restartNeeded', { keys: restart.map(k => isolate(language, byKey[k] ? words.label(byKey[k]) : k)).join(language === 'ar' ? '، ' : ', ') }), { icon: '↻', duration: 10000 })
    else toast.success(message)
  }

  const save = async () => {
    const values: Record<string, string | number | boolean> = {}
    for (const key of dirty) {
      const s = byKey[key]
      if (s.secret && drafts[key] === '') continue          // blank secret: keep the stored one
      const v = toValue(s, drafts[key], t, words.label(s))
      if (typeof v === 'object') { toast.error(v.error); return }
      values[key] = v
    }
    if (!Object.keys(values).length) { setDrafts({}); return }
    setBusy(true)
    try { apply(await platformSettingsApi.save(values), t('settings.saved')) }
    catch (e) { toast.error(detail(e) ?? t('settings.saveFailed')) }
    finally { setBusy(false) }
  }

  const reset = async (key: string) => {
    setBusy(true)
    try {
      apply(await platformSettingsApi.save({ [key]: null }), t('settings.resetDone', { name: isolate(language, words.label(byKey[key])) }))
    } catch (e) { toast.error(detail(e) ?? t('settings.saveFailed')) }
    finally { setBusy(false) }
  }

  const testLlm = async () => {
    setTesting(true)
    const body: { llm_base_url?: string; llm_model?: string; llm_api_key?: string } = {}
    for (const k of ['llm_base_url', 'llm_model', 'llm_api_key'] as const) {
      if (typeof drafts[k] === 'string' && drafts[k] !== '') body[k] = drafts[k] as string
    }
    try {
      const r = await platformSettingsApi.testLlm(body)
      if (r.ok) toast.success(t('settings.testOk', { model: r.model, ms: r.latency_ms }))
      else toast.error(t('settings.testFail', { detail: r.detail }))
    } catch (e) { toast.error(t('settings.testFail', { detail: detail(e) ?? '' })) }
    finally { setTesting(false) }
  }

  if (loadError) return <LoadError what={t('settings.loadWhat')} error={loadError} onRetry={load} />
  if (!data) return <LoadingState />

  const q = query.trim().toLowerCase()
  // The words on screen and the server's English both match, so a search
  // typed in either language finds the setting.
  const matches = (s: PlatformSetting) => !q
    || `${words.label(s)} ${words.help(s)} ${s.label} ${s.help} ${s.key}`.toLowerCase().includes(q)
  const visible = data.categories
    .map(c => ({ ...c, settings: c.settings.filter(matches) }))
    .filter(c => c.settings.length)

  return (
    <section aria-labelledby="settings-platform" style={{ marginTop: 28 }}>
      <h2 id="settings-platform" style={{ fontSize: 17, marginBottom: 4 }}>{t('settings.platform.title')}</h2>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>{t('settings.platform.hint')}</p>
      <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder={t('settings.search')}
        aria-label={t('settings.search')} className="dl-field__input" style={{ maxWidth: 360, marginBottom: 12 }} />
      {visible.length === 0 && <p role="status" style={{ fontSize: 13 }}>{t('settings.noMatch', { q: isolate(language, query.trim()) })}</p>}
      {visible.map(c => (
        <details key={c.id} className="card dl-settings__group" open={Boolean(q) || OPEN_BY_DEFAULT.has(c.id)}>
          <summary><h3 style={{ display: 'inline', fontSize: 14 }}>{words.category(c.id, c.label)}</h3>
            <span style={{ color: 'var(--muted)', fontSize: 12 }}> · {c.settings.length}</span></summary>
          {c.id === 'ai' && <LlmEndpointsPanel />}
          {c.settings.map(s => (
            <SettingRow key={s.key} s={s} draft={drafts[s.key]} busy={busy} words={words}
              onChange={d => setDrafts(ds => ({ ...ds, [s.key]: d }))} onReset={() => void reset(s.key)} />
          ))}
          {c.id === 'ai' && (
            <button type="button" className="btn btn-sm" disabled={testing} onClick={() => void testLlm()}>
              {testing ? t('settings.testing') : t('settings.testLlm')}
            </button>
          )}
        </details>
      ))}
      {dirty.length > 0 && (
        <div className="dl-settings__bar" role="region" aria-label={t('settings.unsaved', { n: dirty.length })}>
          <span>{t('settings.unsaved', { n: dirty.length })}</span>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => setDrafts({})}>{t('settings.discard')}</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void save()}>
            {busy ? t('settings.saving') : t('settings.save')}
          </button>
        </div>
      )}
    </section>
  )
}

export default function Settings({ scope = 'all' }: { scope?: 'all' | 'platform' }) {
  const t = useT()
  const user = useContext(AuthContext)?.user
  const isOrgAdmin = !!user?.role?.is_org_admin
  const isSuperAdmin = !!user?.is_super_admin
  return (
    <div style={{ maxWidth: 880, paddingBottom: 72 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{scope === 'platform' ? t('nav.platformSettings') : t('settings.title')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>{t('settings.subtitle')}</p>

      {scope === 'all' && isOrgAdmin && (
        <section aria-labelledby="settings-org" style={{ marginTop: 20 }}>
          <h2 id="settings-org" style={{ fontSize: 17, marginBottom: 4 }}>{t('settings.org.title')}</h2>
          <BasemapSettings headingLevel={3} />
          <div className="card" style={{ padding: 16, marginTop: 12 }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>{t('settings.org.more')}</h3>
            <ul className="dl-settings__links">
              {ORG_LINKS.map(l => <li key={l.to}><Link to={l.to}>{t(l.key)}</Link></li>)}
            </ul>
          </div>
        </section>
      )}

      {isSuperAdmin ? <PlatformSettings /> : (
        scope === 'all' && <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 24 }}>{t('settings.platform.onlyAdmins')}</p>
      )}
    </div>
  )
}
