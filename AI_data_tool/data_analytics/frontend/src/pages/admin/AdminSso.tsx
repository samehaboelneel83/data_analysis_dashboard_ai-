import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
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
      toast.error(protocol === 'oidc' ? 'Domain and issuer URL are required'
                                      : 'Domain and IdP entity ID are required')
      return
    }
    const body: SsoConfig = { protocol, enabled, email_domain: domain.trim(), issuer: issuer.trim() }
    if (protocol === 'oidc') {
      if (!clientId.trim()) { toast.error('Client ID is required'); return }
      if (!configured && !secret.trim()) { toast.error('A client secret is required'); return }
      body.client_id = clientId.trim()
      body.client_secret = secret.trim() ? secret.trim() : REDACTED
    } else {
      if (!ssoUrl.trim() || !cert.trim()) { toast.error('SSO URL and signing certificate are required'); return }
      body.config = { sso_url: ssoUrl.trim(), x509_cert: cert.trim() }
    }
    setSaving(true)
    try {
      await ssoApi.putConfig(body)
      toast.success('SSO settings saved')
      load()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save SSO settings')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!await confirm({
      title: 'Remove SSO for this organization?',
      body: 'Everyone signs in with a password instead. Anyone without one must reset it before they can get back in.',
      confirmLabel: 'Remove SSO',
    })) return
    try {
      await ssoApi.deleteConfig()
      toast.success('SSO removed')
      setConfigured(false); setHasSecret(false); setSecret('')
      setIssuer(''); setClientId(''); setSsoUrl(''); setCert(''); setDomain('')
    } catch { toast.error('Could not remove SSO') }
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

  if (loading) return <div><LoadingState /></div>
  if (loadError != null) return <div style={{ maxWidth: 640 }}><LoadError what="SSO settings" error={loadError} onRetry={load} /></div>

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
              {p === 'oidc' ? 'OpenID Connect' : 'SAML 2.0'}
            </button>
          ))}
        </div>
      ), protocol === 'oidc'
        ? 'Azure AD / Entra, Okta, Google, Auth0, Keycloak.'
        : 'ADFS, Shibboleth, or any SAML 2.0 IdP.')}

      {field(t('sso.emailDomain'), <input style={inp} value={domain}
        onChange={e => setDomain(e.target.value)} placeholder="acme.com" />,
        t('sso.emailDomainHint'))}

      {protocol === 'oidc' ? (
        <>
          {field('Issuer URL', <input style={inp} value={issuer}
            onChange={e => setIssuer(e.target.value)}
            placeholder="https://login.microsoftonline.com/<tenant>/v2.0" />,
            'Its /.well-known/openid-configuration is read automatically.')}
          {field('Client ID', <input style={inp} value={clientId}
            onChange={e => setClientId(e.target.value)} placeholder="application (client) id"
            autoComplete="off" name="sso-client-id" />)}
          {field('Client secret', <input style={inp} type="password" value={secret}
            onChange={e => setSecret(e.target.value)}
            autoComplete="new-password" name="sso-client-secret"
            placeholder={hasSecret ? '•••••••• (unchanged)' : 'client secret'} />,
            hasSecret ? 'Leave blank to keep the stored secret.' : undefined)}
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 16 }}>
            Redirect URI for your IdP: <code>{callback}</code>
          </p>
        </>
      ) : (
        <>
          {field('IdP entity ID', <input style={inp} value={issuer}
            onChange={e => setIssuer(e.target.value)} placeholder="https://idp.example.com/entity" />,
            'The IssuerName / EntityID from your IdP metadata.')}
          {field('SSO URL', <input style={inp} value={ssoUrl}
            onChange={e => setSsoUrl(e.target.value)} placeholder="https://idp.example.com/sso" />,
            'The IdP’s HTTP-Redirect SingleSignOnService location.')}
          {field('Signing certificate (X.509)', <textarea style={{ ...inp, minHeight: 120, fontFamily: 'monospace' }}
            value={cert} onChange={e => setCert(e.target.value)}
            placeholder="-----BEGIN CERTIFICATE----- … or the bare base64 from IdP metadata" />,
            'The public certificate the IdP signs assertions with.')}
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 16 }}>
            Give your IdP this ACS URL: <code>{acs}</code> · SP metadata:{' '}
            <code>{API_ORIGIN}/api/v1/auth/sso/saml/metadata</code>
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
