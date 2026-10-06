import { useEffect, useState } from 'react'
import { Copy, Link2, TriangleAlert } from 'lucide-react'
import { shareLinksApi, embedConfigsApi } from '../../../services/api'
import { useConfirm } from '../../ui/ConfirmDialog'
import { useT } from '../../../i18n'
import { localDigits } from '../../../lib/arabicFormats'

/**
 * The two link-based ways in, from v1's Guest links dialog, inside the Share
 * dialog (redesign 7c). Both keep v1's model:
 *  - a guest link's authority is the URL itself: several links, each shown
 *    ONCE (the server keeps a hash), 1–90 days, seen with the sharer's data
 *    permissions, revocable;
 *  - an embed's authority is a JWT the HOST signs with a secret shown once;
 *    its scope is whatever the host puts in the token, never the browser.
 */

const EXPIRY = ['1', '7', '30', '90'] as const
const date = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '')

export function GuestLinks({ reportId, blockedReason }: { reportId: number; blockedReason?: string | null }) {
  const t = useT()
  const confirm = useConfirm()
  const [links, setLinks] = useState<{ id: number; creator: string; expires_at: string; active: boolean; pinned: boolean;
    access_count: number; last_access_at: string | null }[]>([])
  const [days, setDays] = useState<string>('7')
  const [pinned, setPinned] = useState(false)
  const [minted, setMinted] = useState('')
  // Which link the one-time URL belongs to, so revoking it takes the URL away
  // (QA2 Visual 9: the dead address stayed on screen).
  const [mintedId, setMintedId] = useState<number | null>(null)
  // Revoked and expired links stay as the record of who had access, folded.
  const [showOff, setShowOff] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const refresh = () => Promise.resolve().then(() => shareLinksApi.list(reportId)).then(r => setLinks(r ?? [])).catch(() => setLinks([]))
  useEffect(() => { void refresh() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [reportId])

  const mint = async () => {
    setError('')
    try {
      const r = await shareLinksApi.create(reportId, Number(days) || 7, pinned)
      setMinted(`${window.location.origin}/shared/${r.token}`)
      setMintedId(r.id ?? null)
      setCopied(false)
      void refresh()
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('shx.gl.failed'))
    }
  }

  return (
    <div data-testid="guest-links">
      <div className="shx-warn"><TriangleAlert size={15} aria-hidden /><span>{t('shx.gl.warning')}</span></div>
      {blockedReason ? (
        <p className="shx-note" role="note">{blockedReason}</p>
      ) : (<>
        <div className="shx-row">
          <span className="lb">{t('shx.gl.expires')}</span>
          <div className="shx-seg" role="group" aria-label={t('shx.gl.expires')}>
            {EXPIRY.map(d => (
              <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)}>
                {t(d === '1' ? 'shx.gl.day' : 'shx.gl.days', { n: localDigits(d) })}
              </button>
            ))}
          </div>
        </div>
        <div className="shx-row">
          <label className="shx-ck">
            <input type="checkbox" checked={pinned} onChange={e => setPinned(e.target.checked)} />
            <span>{t('shx.gl.pin')} <span style={{ color: 'var(--muted)' }}>{t('shx.gl.pinWhy')}</span></span>
          </label>
        </div>
        <div className="shx-row">
          <button type="button" className="btn btn-ghost" style={{ border: '1px solid var(--mc-border-strong)' }} onClick={() => void mint()}>
            <Link2 size={14} aria-hidden />{t('shx.gl.create')}
          </button>
        </div>
        {error && <p className="shx-err" role="alert">{error}</p>}
      </>)}

      {minted && (
        <div className="shx-once">
          <p>{t('shx.gl.once')}</p>
          <div className="shx-link" style={{ marginTop: 0 }}>
            <div className="shx-url" dir="ltr"><input readOnly value={minted} aria-label={t('shx.gl.url')} onFocus={e => e.target.select()} /></div>
            <button type="button" className="btn btn-primary" onClick={() => { navigator.clipboard?.writeText(minted); setCopied(true) }}>
              <Copy size={14} aria-hidden />{copied ? t('shx.copied') : t('shx.copy')}
            </button>
          </div>
        </div>
      )}

      {links.length > 0 && (
        <ul className="shx-list" aria-label={t('shx.gl.list')}>
          {links.filter(l => l.active || showOff).map(l => (
            <li key={l.id} data-off={!l.active || undefined}>
              <div className="tx">
                <b dir="auto">{l.creator}</b>
                <span>
                  {l.active ? t('shx.gl.expiresOn', { date: date(l.expires_at) }) : t('shx.gl.inactive')}
                  {l.pinned ? ` · ${t('shx.gl.pinned')}` : ''}
                  {' · '}{t(l.access_count === 1 ? 'shx.gl.view' : 'shx.gl.views', { n: localDigits(String(l.access_count)) })}
                  {l.last_access_at ? ` · ${t('shx.gl.last', { date: date(l.last_access_at) })}` : ''}
                </span>
              </div>
              {l.active && (
                <button type="button" className="btn btn-ghost btn-sm" aria-label={t('shx.gl.revokeAria', { id: l.id })}
                  onClick={async () => {
                    // The one irreversible action here, and the only one whose
                    // reach is OUTSIDE the system: the URL is already with people
                    // who are not users. The view count says whether it is live.
                    if (!await confirm({
                      title: t('shx.gl.revokeTitle'),
                      body: l.access_count > 0
                        ? t('shx.gl.revokeUsed', { n: localDigits(String(l.access_count)) })
                        : t('shx.gl.revokeUnused'),
                      confirmLabel: t('shx.gl.revoke'),
                    })) return
                    await shareLinksApi.revoke(reportId, l.id)
                    if (l.id === mintedId) { setMinted(''); setMintedId(null) }
                    void refresh()
                  }}>{t('shx.gl.revoke')}</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {links.some(l => !l.active) && (
        <button type="button" className="shx-more" aria-expanded={showOff} onClick={() => setShowOff(v => !v)}>
          {showOff ? t('shx.gl.hideOff')
            : t(links.filter(l => !l.active).length === 1 ? 'shx.gl.showOffOne' : 'shx.gl.showOff', { n: localDigits(String(links.filter(l => !l.active).length)) })}
        </button>
      )}
    </div>
  )
}

type EmbedConfigRow = { id: number; name: string; allowed_origins: string[]; enabled: boolean; created_at: string; last_used_at: string | null }

export function EmbedSection({ reportId }: { reportId: number }) {
  const t = useT()
  const [configs, setConfigs] = useState<EmbedConfigRow[]>([])
  const [name, setName] = useState('')
  const [origins, setOrigins] = useState('')
  const [minted, setMinted] = useState<{ id: number; secret: string } | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [error, setError] = useState('')

  const refresh = () => Promise.resolve().then(() => embedConfigsApi.list(reportId)).then(r => setConfigs(r ?? [])).catch(() => setConfigs([]))
  useEffect(() => { void refresh() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [reportId])

  const create = async () => {
    setError('')
    try {
      const r = await embedConfigsApi.create(reportId, name || 'default', origins.split(',').map(o => o.trim()).filter(Boolean))
      setMinted({ id: r.id, secret: r.secret })
      setName(''); setOrigins('')
      void refresh()
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('shx.em.failed'))
    }
  }
  const copy = (label: string, text: string) => {
    navigator.clipboard?.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(c => (c === label ? null : c)), 1500)
  }

  const embedUrl = `${window.location.origin}/embed?token=<TOKEN_FROM_YOUR_SERVER>`
  const iframe = `<iframe src="${embedUrl}" style="width:100%;height:640px;border:0" allow="clipboard-write"></iframe>`
  const python = minted ? `import time, jwt  # pip install pyjwt

payload = {
    "cfg": ${minted.id},
    "exp": int(time.time()) + 3600,  # max 24h ahead
    "filters": [{"column": "region", "op": "eq", "value": "US"}],  # optional, scopes every widget
    "viewer_email": "viewer@customer.example.com",  # optional, expands USEREMAIL()
}
token = jwt.encode(payload, "${minted.secret}", algorithm="HS256")
# Hand the token to the browser as ${window.location.origin}/embed?token=<token>` : ''
  const node = minted ? `const jwt = require('jsonwebtoken') // npm install jsonwebtoken

const token = jwt.sign({
  cfg: ${minted.id},
  filters: [{ column: 'region', op: 'eq', value: 'US' }], // optional, scopes every widget
  viewer_email: 'viewer@customer.example.com', // optional, expands USEREMAIL()
}, '${minted.secret}', { algorithm: 'HS256', expiresIn: '1h' }) // max 24h
// Hand \`token\` to the browser as ${window.location.origin}/embed?token=<token>` : ''

  const code = (label: string, text: string, title: string) => (
    <>
      <div className="shx-sub">{title}</div>
      <div className="shx-code" dir="ltr">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => copy(label, text)}>
          <Copy size={13} aria-hidden />{copied === label ? t('shx.copied') : t('shx.copy')}
        </button>
        <pre><code>{text}</code></pre>
      </div>
    </>
  )

  return (
    <div data-testid="embed-section">
      <div className="shx-info"><TriangleAlert size={15} aria-hidden /><span>{t('shx.em.intro')}</span></div>
      <div className="shx-row" style={{ alignItems: 'flex-end' }}>
        <div style={{ flex: 1, minWidth: 160 }}>
          <label className="shx-lbl" htmlFor="embed-name">{t('shx.em.name')}</label>
          <input id="embed-name" className="shx-in" value={name} onChange={e => setName(e.target.value)} placeholder="customer-portal" dir="ltr" />
        </div>
        <div style={{ flex: 1.4, minWidth: 200 }}>
          <label className="shx-lbl" htmlFor="embed-origins">{t('shx.em.origins')}</label>
          <input id="embed-origins" className="shx-in" value={origins} onChange={e => setOrigins(e.target.value)} placeholder="https://app.customer.com" dir="ltr" />
        </div>
        <button type="button" className="btn btn-primary" style={{ height: 40 }} onClick={() => void create()}>{t('shx.em.create')}</button>
      </div>
      {error && <p className="shx-err" role="alert">{error}</p>}

      {minted && (
        <div className="shx-once">
          <p>{t('shx.em.once')}</p>
          <div className="shx-link" style={{ marginTop: 0 }}>
            <div className="shx-url" dir="ltr"><input readOnly value={minted.secret} aria-label={t('shx.em.secret')} onFocus={e => e.target.select()} /></div>
            <button type="button" className="btn btn-primary" onClick={() => copy('secret', minted.secret)}>
              <Copy size={14} aria-hidden />{copied === 'secret' ? t('shx.copied') : t('shx.copy')}
            </button>
          </div>
          {code('iframe', iframe, t('shx.em.iframe'))}
          {code('python', python, t('shx.em.python'))}
          {code('node', node, t('shx.em.node'))}
        </div>
      )}

      {configs.length > 0 && (
        <ul className="shx-list" aria-label={t('shx.em.list')}>
          {configs.map(c => (
            <li key={c.id} data-off={!c.enabled || undefined}>
              <div className="tx">
                <b dir="auto">{c.name}</b>
                <span>
                  {t(c.enabled ? 'shx.em.enabled' : 'shx.em.disabled')}
                  {c.allowed_origins.length > 0 && ` · ${t('shx.em.nOrigins', { n: localDigits(String(c.allowed_origins.length)) })}`}
                  {c.last_used_at && ` · ${t('shx.gl.last', { date: date(c.last_used_at) })}`}
                </span>
              </div>
              <button type="button" className="btn btn-ghost btn-sm" aria-label={t(c.enabled ? 'shx.em.disableAria' : 'shx.em.enableAria', { id: c.id })}
                onClick={() => embedConfigsApi.setEnabled(reportId, c.id, !c.enabled).then(refresh)}>
                {t(c.enabled ? 'shx.em.disable' : 'shx.em.enable')}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" aria-label={t('shx.em.deleteAria', { id: c.id })}
                onClick={() => embedConfigsApi.delete(reportId, c.id).then(refresh)}>{t('shx.em.delete')}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
