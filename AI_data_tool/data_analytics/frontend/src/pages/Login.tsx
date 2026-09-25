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

  // The card takes the width it is given, up to 380px, so it keeps a gutter on
  // a 390px phone instead of touching both edges. Every value is a class in
  // index.css (.dl-login*), so the page follows the theme like the shell does.
  return (
    <div className="dl-login">
      <div className="dl-login__lang"><LanguageSwitcher /></div>
      <form onSubmit={handleSubmit} className="dl-login__card">
        <div className="dl-login__brand">
          <span className="dl-rail__mark" aria-hidden>D</span>
          <span className="dl-rail__wordmark">datalytics</span>
        </div>
        <h1 className="dl-login__title">{t('login.title')}</h1>
        <p className="dl-login__sub">{t('login.subtitle')}</p>

        <label className="dl-field">
          <span className="dl-field__label">{t('login.email')}</span>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
            autoFocus autoComplete="username" className="dl-field__input" />
        </label>
        <label className="dl-field">
          <span className="dl-field__label">{t('login.password')}</span>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            autoComplete="current-password" className="dl-field__input" />
        </label>
        <button type="submit" className="btn btn-primary dl-login__submit" disabled={submitting}>
          {submitting ? t('login.signingIn') : t('login.signIn')}
        </button>
        <div className="dl-login__or" role="separator">
          <span>{t('login.or')}</span>
        </div>
        <button type="button" className="btn btn-ghost dl-login__submit" onClick={handleSso} disabled={ssoBusy}>
          {ssoBusy ? t('login.redirecting') : t('login.sso')}
        </button>
      </form>
    </div>
  )
}
