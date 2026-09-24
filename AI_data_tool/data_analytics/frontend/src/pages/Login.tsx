import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { ssoApi } from '../services/api'
import toast from 'react-hot-toast'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { useT, type MessageKey } from '../i18n'

const SSO_KEYS: Record<string, MessageKey> = {
  not_configured: 'login.sso.not_configured',
  provider_unreachable: 'login.sso.provider_unreachable',
  denied: 'login.sso.denied',
  no_account: 'login.sso.no_account',
  no_id_token: 'login.sso.no_id_token',
  email_unverified: 'login.sso.email_unverified',
  validation_failed: 'login.sso.validation_failed',
  missing_token: 'login.sso.missing_token',
}

export default function Login() {
  const { login, user } = useAuth()
  const t = useT()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [ssoBusy, setSsoBusy] = useState(false)

  useEffect(() => {
    const err = new URLSearchParams(window.location.search).get('sso_error')
    if (err) {
      toast.error(SSO_KEYS[err] ? t(SSO_KEYS[err]) : t('login.ssoFailed'))
      window.history.replaceState({}, '', '/login')   // clear the query so a refresh is clean
    }
  }, [t])

  if (user) {
    // Already authenticated (e.g. navigated back to /login manually) — bounce home.
    window.location.replace('/')
    return null
  }

  const inp = {
    style: {
      width: '100%', fontSize: 13, padding: '8px 10px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)',
    },
  }

  const handleSso = async () => {
    if (!email.trim()) {
      toast.error(t('login.ssoNeedEmail'))
      return
    }
    setSsoBusy(true)
    try {
      const { sso, protocol } = await ssoApi.discover(email.trim())
      if (!sso) {
        toast.error(t('login.ssoNone'))
        return
      }
      window.location.href = ssoApi.loginUrl(email.trim(), protocol)   // hand off to the IdP
    } catch {
      toast.error(t('login.ssoStartFail'))
    } finally {
      setSsoBusy(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      toast.error(t('login.needBoth'))
      return
    }
    setSubmitting(true)
    try {
      await login(email.trim(), password)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t('login.invalid'))
    } finally {
      setSubmitting(false)
    }
  }

  // The card was a fixed 360px wide with no gutter of its own: on a 390px phone
  // it touched both edges, and on anything narrower it ran off the screen with
  // no sideways scroll to reach it. It now takes the width it is given, up to
  // the same 360.
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)', padding: 16, boxSizing: 'border-box' }}>
      <form onSubmit={handleSubmit} style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 12, padding: 'clamp(20px, 6vw, 32px)', width: '100%', maxWidth: 360,
        boxSizing: 'border-box',
      }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <LanguageSwitcher />
        </div>
        <div style={{ fontWeight: 800, fontSize: 20, color: 'var(--accent)', marginBottom: 24, textAlign: 'center' }}>
          Datalytics
        </div>
        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>{t('login.email')}</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus {...inp} />
        </label>
        <label style={{ display: 'block', marginBottom: 20 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>{t('login.password')}</div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} {...inp} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%' }}>
          {submitting ? t('login.signingIn') : t('login.signIn')}
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '16px 0 12px', color: 'var(--muted)', fontSize: 11 }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          {t('login.or')}
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        </div>
        <button type="button" className="btn" onClick={handleSso} disabled={ssoBusy} style={{ width: '100%' }}>
          {ssoBusy ? t('login.redirecting') : t('login.sso')}
        </button>
      </form>
    </div>
  )
}
