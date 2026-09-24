import { useEffect, useState } from 'react'
import { shareLinksApi, embedConfigsApi } from '../../services/api'
import { useConfirm } from '../ui/ConfirmDialog'
import { useModalDialog } from '../ui/useModalDialog'

type EmbedConfigRow = { id: number; name: string; allowed_origins: string[]; enabled: boolean;
  created_at: string; last_used_at: string | null }

/** Host-signed embed credentials for iframe embedding -- Task E1. Distinct
 * from a guest link: a guest link's authority is the URL itself, while an
 * embed's authority is a signature the HOST APPLICATION computes server-side
 * with a secret shown here exactly once. Scope (filters, viewer identity)
 * is never something this dialog or the browser controls -- it's whatever
 * the host's own backend puts in the JWT it signs. */
function EmbedSection({ reportId }: { reportId: number }) {
  const [configs, setConfigs] = useState<EmbedConfigRow[]>([])
  const [name, setName] = useState('')
  const [origins, setOrigins] = useState('')
  const [minted, setMinted] = useState<{ id: number; secret: string } | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const refresh = () => embedConfigsApi.list(reportId).then(setConfigs).catch(() => setConfigs([]))
  useEffect(() => { refresh() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [reportId])

  const create = async () => {
    const allowedOrigins = origins.split(',').map(o => o.trim()).filter(Boolean)
    const r = await embedConfigsApi.create(reportId, name || 'default', allowedOrigins)
    setMinted({ id: r.id, secret: r.secret })
    setName('')
    setOrigins('')
    refresh()
  }

  const copy = (label: string, text: string) => {
    navigator.clipboard?.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(c => (c === label ? null : c)), 1500)
  }

  const embedUrl = `${window.location.origin}/embed?token=<TOKEN_FROM_YOUR_SERVER>`
  const iframeSnippet = `<iframe src="${embedUrl}" style="width:100%;height:640px;border:0" allow="clipboard-write"></iframe>`
  const pythonSnippet = minted ? `import time, jwt  # pip install pyjwt

payload = {
    "cfg": ${minted.id},
    "exp": int(time.time()) + 3600,  # max 24h ahead
    "filters": [{"column": "region", "op": "eq", "value": "US"}],  # optional, scopes every widget
    "viewer_email": "viewer@customer.example.com",  # optional, expands USEREMAIL()
}
token = jwt.encode(payload, "${minted.secret}", algorithm="HS256")
# Hand the token to the browser as ${window.location.origin}/embed?token=<token>` : ''
  const nodeSnippet = minted ? `const jwt = require('jsonwebtoken') // npm install jsonwebtoken

const token = jwt.sign({
  cfg: ${minted.id},
  filters: [{ column: 'region', op: 'eq', value: 'US' }], // optional, scopes every widget
  viewer_email: 'viewer@customer.example.com', // optional, expands USEREMAIL()
}, '${minted.secret}', { algorithm: 'HS256', expiresIn: '1h' }) // max 24h
// Hand \`token\` to the browser as ${window.location.origin}/embed?token=<token>` : ''

  return (
    <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
      <strong style={{ fontSize: 13 }}>Embed (host-signed)</strong>
      <p style={{ fontSize: 11, color: 'var(--muted)', margin: '4px 0 12px' }}>
        For embedding in YOUR OWN application: your server signs a short-lived JWT with the
        secret below and hands it to the browser -- the browser never sees the secret, and
        every row/filter shown is whatever your server put in that token. Never trust the
        browser with scope.
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="embed-name" style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
            Config name
          </label>
          <input id="embed-name" value={name} onChange={e => setName(e.target.value)}
            placeholder="e.g. customer-portal" style={{ width: 160 }} />
        </div>
        <div>
          <label htmlFor="embed-origins" style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
            Allowed origins (comma-separated, optional)
          </label>
          <input id="embed-origins" value={origins} onChange={e => setOrigins(e.target.value)}
            placeholder="https://app.customer.com" style={{ width: 220 }} />
        </div>
        <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => void create()}>Create embed config</button>
      </div>

      {minted && (
        <div style={{ border: '1px solid var(--accent)', borderRadius: 6, padding: 8, marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 4 }}>
            Copy the secret now — it is shown only once and cannot be recovered.
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <input readOnly value={minted.secret} aria-label="Embed secret" style={{ flex: 1, fontSize: 11 }}
              onFocus={e => e.target.select()} />
            <button className="btn" style={{ fontSize: 11 }} onClick={() => copy('secret', minted.secret)}>
              {copied === 'secret' ? 'Copied ✓' : 'Copy'}
            </button>
          </div>

          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>Iframe snippet</div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <textarea readOnly value={iframeSnippet} rows={2}
              style={{ flex: 1, fontSize: 10, fontFamily: 'monospace', resize: 'vertical' }} />
            <button className="btn" style={{ fontSize: 11 }} onClick={() => copy('iframe', iframeSnippet)}>
              {copied === 'iframe' ? 'Copied ✓' : 'Copy'}
            </button>
          </div>

          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>
            Sample server-side token generation — Python
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <textarea readOnly value={pythonSnippet} rows={8}
              style={{ flex: 1, fontSize: 10, fontFamily: 'monospace', resize: 'vertical' }} />
            <button className="btn" style={{ fontSize: 11 }} onClick={() => copy('python', pythonSnippet)}>
              {copied === 'python' ? 'Copied ✓' : 'Copy'}
            </button>
          </div>

          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>
            Sample server-side token generation — Node
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <textarea readOnly value={nodeSnippet} rows={8}
              style={{ flex: 1, fontSize: 10, fontFamily: 'monospace', resize: 'vertical' }} />
            <button className="btn" style={{ fontSize: 11 }} onClick={() => copy('node', nodeSnippet)}>
              {copied === 'node' ? 'Copied ✓' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {configs.length > 0 && (
        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 160, overflowY: 'auto' }}>
          {configs.map(c => (
            <li key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
              border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px', opacity: c.enabled ? 1 : 0.55 }}>
              <span style={{ flex: 1 }}>
                {c.name} · {c.enabled ? 'enabled' : 'disabled'}
                {c.allowed_origins.length > 0 && ` · ${c.allowed_origins.length} origin(s)`}
                {c.last_used_at && ` · last used ${new Date(c.last_used_at).toLocaleDateString()}`}
              </span>
              <button aria-label={`${c.enabled ? 'Disable' : 'Enable'} embed config ${c.id}`} className="btn" style={{ fontSize: 10 }}
                onClick={() => embedConfigsApi.setEnabled(reportId, c.id, !c.enabled).then(refresh)}>
                {c.enabled ? 'Disable' : 'Enable'}
              </button>
              <button aria-label={`Delete embed config ${c.id}`} className="btn" style={{ fontSize: 10 }}
                onClick={() => embedConfigsApi.delete(reportId, c.id).then(refresh)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Guest-link management. The minted URL is shown exactly once (the server
 * stores only a hash), and the warning is explicit: anyone holding the link
 * sees the report with THE SHARER'S data permissions.
 */
export default function ShareLinksDialog({ reportId, onClose }: {
  reportId: number
  onClose: () => void
}) {
  const [links, setLinks] = useState<{ id: number; creator: string; expires_at: string; active: boolean; pinned: boolean;
    access_count: number; last_access_at: string | null }[]>([])
  const [days, setDays] = useState('7')
  const [pinned, setPinned] = useState(false)
  const [minted, setMinted] = useState('')
  const [copied, setCopied] = useState(false)

  const confirm = useConfirm()
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)

  const refresh = () => shareLinksApi.list(reportId).then(setLinks).catch(() => setLinks([]))
  useEffect(() => { refresh() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [reportId])

  const mint = async () => {
    const r = await shareLinksApi.create(reportId, Number(days) || 7, pinned)
    setMinted(`${window.location.origin}/shared/${r.token}`)
    setCopied(false)
    refresh()
  }

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Guest links"
          onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 480, maxWidth: '92vw' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong style={{ fontSize: 13 }}>Guest links</strong>
          <button onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
          Guest viewers see data <strong>with YOUR data permissions</strong> — anyone with the link sees
          this report read-only, as you see it. (A teammate who opens the link while already signed
          into this organisation sees it with their own permissions instead.) Links can be revoked
          here at any time.
        </p>

        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
          <div>
            <label htmlFor="share-days" style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
              Expires after (days)
            </label>
            <input id="share-days" type="number" min={1} max={90} value={days}
              onChange={e => setDays(e.target.value)} style={{ width: 90 }} />
          </div>
          <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => void mint()}>Create guest link</button>
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={pinned} onChange={e => setPinned(e.target.checked)} />
          Pin current layout
          <span style={{ color: 'var(--muted)' }}>— freezes pages/widgets as they are now; the data guests see still updates live</span>
        </label>

        {minted && (
          <div style={{ border: '1px solid var(--accent)', borderRadius: 6, padding: 8, marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 4 }}>
              Copy it now — this URL is shown only once.
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <input readOnly value={minted} aria-label="Guest link URL" style={{ flex: 1, fontSize: 11 }}
                onFocus={e => e.target.select()} />
              <button className="btn" style={{ fontSize: 11 }}
                onClick={() => { navigator.clipboard?.writeText(minted); setCopied(true) }}>
                {copied ? 'Copied ✓' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        {links.length > 0 && (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
            {links.map(l => (
              <li key={l.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
                border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px', opacity: l.active ? 1 : 0.55 }}>
                <span style={{ flex: 1 }}>
                  {l.creator} · {l.active ? `expires ${new Date(l.expires_at).toLocaleDateString()}` : 'inactive'}
                  {l.pinned && ' · pinned'}
                  {' · '}{l.access_count} view{l.access_count === 1 ? '' : 's'}
                  {l.last_access_at && ` (last ${new Date(l.last_access_at).toLocaleDateString()})`}
                </span>
                {l.active && (
                  <button aria-label={`Revoke link ${l.id}`} className="btn" style={{ fontSize: 10 }}
                    onClick={async () => {
                      // The one irreversible action in this dialog, and the only
                      // one whose blast radius sits OUTSIDE the system: the URL
                      // has already been sent to people who are not users here,
                      // and revoking breaks it for all of them with no way to
                      // put it back -- a new link is a different URL. The view
                      // count is named because it is the difference between
                      // revoking a link nobody used and cutting off live access.
                      if (!await confirm({
                        title: 'Revoke this guest link?',
                        body: l.access_count > 0
                          ? `It has been opened ${l.access_count} time${l.access_count === 1 ? '' : 's'}. Anyone using it loses access immediately, and the URL cannot be restored — a replacement link is a different address.`
                          : 'The URL stops working immediately and cannot be restored — a replacement link is a different address.',
                        confirmLabel: 'Revoke link',
                      })) return
                      await shareLinksApi.revoke(reportId, l.id)
                      refresh()
                    }}>Revoke</button>
                )}
              </li>
            ))}
          </ul>
        )}

        <EmbedSection reportId={reportId} />
      </div>
    </div>
  )
}
