import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { richNodes } from '../../i18n/pages/adminPlatform'
import toast from 'react-hot-toast'
import { apiOrigin, ssoApi, type SsoConfig } from '../../services/api'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const REDACTED = '__SECRET_UNCHANGED__'
// Absolute, because an admin PASTES these into their identity provider.
// Under the same-origin production build this resolves to the browser's
// own address rather than a useless relative path.
const API_ORIGIN = apiOrigin()
/** Protocol names, the same in every language. */
const PROTOCOL_NAME = { oidc: 'OpenID Connect', saml: 'SAML 2.0' } as const

/** Org-admin screen to configure this organization's identity provider — OpenID Connect
 *  or SAML 2.0. SSO authenticates users an admin has already created here; it never
 *  provisions new accounts. Secrets are write-only (stored, never returned). */
export default function AdminSso() {
  const t = useT()
  const confirm = useConfirm()
  const [protocol, setProtocol] = useState<'oidc' | 'saml'>('oidc')
  const [enabled, setEnabled] = useState(true)
  const [domain, setDomain] = useState('')
  const [issuer, setIssuer] = useState('')          // OIDC issuer, or SAML IdP entity ID
  const [clientId, setClientId] = useState('')      // OIDC
  const [secret, setSecret] = useState('')          // OIDC, typed only when (re)setting
  const [hasSecret, setHasSecret] = useState(false)
  const [ssoUrl, setSsoUrl] = useState('')          // SAML
  const [cert, setCert] = useState('')              // SAML signing certificate
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    setLoadError(null)
    ssoApi.getConfig()
      .then(c => {
        setConfigured(!!c.configured)
        const p = (c.protocol as 'oidc' | 'saml') || 'oidc'
        setProtocol(p)
        setEnabled(c.enabled ?? true)
        setDomain(c.email_domain ?? '')
        setIssuer(c.issuer ?? '')
        setClientId(c.client_id ?? '')
        setHasSecret(c.client_secret === REDACTED)
        setSecret('')
        const cfg = (c.config ?? {}) as Record<string, string>
        setSsoUrl(cfg.sso_url ?? '')
        setCert(cfg.x509_cert ?? '')
      })
      // Persistent inline banner, not a toast that fades: a page that only ever
      // shows one form is exactly the "we could not ask" case LoadError exists
      // for, not a transient action failure.
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const save = async () => {
    if (!domain.trim() || !issuer.trim()) {
      toast.error(protocol === 'oidc' ? t('pg.adminPlatform.sso.reqIssuer')
                                      : t('pg.adminPlatform.sso.reqEntity'))
      return
    }
    const body: SsoConfig = { protocol, enabled, email_domain: domain.trim(), issuer: issuer.trim() }
    if (protocol === 'oidc') {
      if (!clientId.trim()) { toast.error(t('pg.adminPlatform.sso.reqClientId')); return }
      if (!configured && !secret.trim()) { toast.error(t('pg.adminPlatform.sso.reqSecret')); return }
      body.client_id = clientId.trim()
      body.client_secret = secret.trim() ? secret.trim() : REDACTED
    } else {
      if (!ssoUrl.trim() || !cert.trim()) { toast.error(t('pg.adminPlatform.sso.reqSaml')); return }
      body.config = { sso_url: ssoUrl.trim(), x509_cert: cert.trim() }
    }
    setSaving(true)
    try {
      await ssoApi.putConfig(body)
      toast.success(t('pg.adminPlatform.sso.saved'))
      load()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.sso.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!await confirm({
      title: t('pg.adminPlatform.sso.removeTitle'),
      body: t('pg.adminPlatform.sso.removeBody'),
      confirmLabel: t('sso.remove'),
    })) return
    try {
      await ssoApi.deleteConfig()
      toast.success(t('pg.adminPlatform.sso.removed'))
      setConfigured(false); setHasSecret(false); setSecret('')
      setIssuer(''); setClientId(''); setSsoUrl(''); setCert(''); setDomain('')
    } catch { toast.error(t('pg.adminPlatform.sso.removeFailed')) }
  }

  const inp: React.CSSProperties = fieldStyle
  const field = (label: string, node: React.ReactNode, hint?: string) => (
    <label style={{ display: 'block', marginBottom: 16 }}>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>{label}</div>
      {node}
      {hint && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>{hint}</div>}
    </label>
  )
  const acs = `${API_ORIGIN}/api/v1/auth/sso/saml/acs`
  const callback = `${API_ORIGIN}/api/v1/auth/sso/oidc/callback`
  const metadata = `${API_ORIGIN}/api/v1/auth/sso/saml/metadata`

  if (loading) return <div><LoadingState /></div>
  if (loadError != null) return <div style={{ maxWidth: 640 }}><LoadError what={t('pg.adminPlatform.sso.loadWhat')}
    title={t('pg.adminPlatform.loadErr', { what: t('pg.adminPlatform.sso.loadWhat') })} retryLabel={t('pg.adminPlatform.retry')}
    error={loadError} onRetry={load} /></div>

  return (
    <div style={{ maxWidth: 640 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.sso')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 20 }}>
        {t('sso.subtitle')}
      </p>

      {field(t('sso.protocol'), (
        // One of two, always one on: a segmented control, like the other
        // either/or switches -- two primary-styled buttons read as two actions.
        <div role="group" aria-label={t('sso.protocol')} className="dl-seg" style={{ display: 'flex' }}>
          {(['oidc', 'saml'] as const).map(p => (
            <button key={p} type="button" aria-pressed={protocol === p}
              className={`dl-seg__btn${protocol === p ? ' dl-seg__btn--on' : ''}`}
              onClick={() => setProtocol(p)} style={{ flex: 1, justifyContent: 'center' }}>
              {PROTOCOL_NAME[p]}
            </button>
          ))}
        </div>
      ), protocol === 'oidc'
        ? 'Azure AD / Entra, Okta, Google, Auth0, Keycloak.' // i18n-ok: product names
        : t('pg.adminPlatform.sso.samlIdps'))}

      {field(t('sso.emailDomain'), <input style={inp} value={domain}
        onChange={e => setDomain(e.target.value)} placeholder="acme.com" dir="ltr" />, // i18n-ok
        t('sso.emailDomainHint'))}

      {protocol === 'oidc' ? (
        <>
          {field(t('pg.adminPlatform.sso.issuer'), <input style={inp} value={issuer} dir="ltr"
            onChange={e => setIssuer(e.target.value)}
            placeholder="https://login.microsoftonline.com/<tenant>/v2.0" />, // i18n-ok: a URL
            t('pg.adminPlatform.sso.issuerHint'))}
          {field(t('pg.adminPlatform.sso.clientId'), <input style={inp} value={clientId} dir="ltr"
            onChange={e => setClientId(e.target.value)} placeholder={t('pg.adminPlatform.sso.clientIdPh')}
            autoComplete="off" name="sso-client-id" />)}
          {field(t('pg.adminPlatform.sso.clientSecret'), <input style={inp} type="password" value={secret}
            onChange={e => setSecret(e.target.value)}
            autoComplete="new-password" name="sso-client-secret"
            placeholder={hasSecret ? t('pg.adminPlatform.sso.secretPhKeep') : t('pg.adminPlatform.sso.secretPh')} />,
            hasSecret ? t('pg.adminPlatform.sso.secretKeepHint') : undefined)}
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 16 }}>
            {richNodes(t('pg.adminPlatform.sso.redirect'), { url: <code dir="ltr">{callback}</code> })}
          </p>
        </>
      ) : (
        <>
          {field(t('pg.adminPlatform.sso.entityId'), <input style={inp} value={issuer} dir="ltr"
            onChange={e => setIssuer(e.target.value)} placeholder="https://idp.example.com/entity" />, // i18n-ok: a URL
            t('pg.adminPlatform.sso.entityHint'))}
          {field(t('pg.adminPlatform.sso.ssoUrl'), <input style={inp} value={ssoUrl} dir="ltr"
            onChange={e => setSsoUrl(e.target.value)} placeholder="https://idp.example.com/sso" />, // i18n-ok: a URL
            t('pg.adminPlatform.sso.ssoUrlHint'))}
          {field(t('pg.adminPlatform.sso.cert'), <textarea style={{ ...inp, minHeight: 120, fontFamily: 'monospace' }}
            value={cert} onChange={e => setCert(e.target.value)} dir="ltr"
            placeholder={t('pg.adminPlatform.sso.certPh')} />,
            t('pg.adminPlatform.sso.certHint'))}
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 16 }}>
            {richNodes(t('pg.adminPlatform.sso.acs'), {
              acs: <code dir="ltr">{acs}</code>,
              meta: <code dir="ltr">{metadata}</code>,
            })}
          </p>
        </>
      )}

      {field('', <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
        <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
        {t('sso.enabled')}
      </label>)}

      <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? t('sso.saving') : t('sso.save')}
        </button>
        {configured && <button className="btn" onClick={remove}>{t('sso.remove')}</button>}
      </div>
    </div>
  )
}
