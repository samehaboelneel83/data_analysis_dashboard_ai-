import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { AlertCircle, ArrowRight, Eye, EyeOff, Loader2, Moon, Sun } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useDirection } from '../contexts/DirectionContext'
import { ssoApi } from '../services/api'
import LanguageSwitcher from '../components/LanguageSwitcher'
import BrandIllustration from '../components/auth/BrandIllustration'
import { useT, type MessageKey } from '../i18n'
import './login.css'

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

// Deliberately lenient: dev and on-prem logins use hosts like
// admin@datalytics.local, so anything shaped name@host is accepted here and
// the server stays the judge of whether the account exists.
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+$/

type FieldErrors = { email?: MessageKey; password?: MessageKey }

function checkEmail(v: string): MessageKey | undefined {
  if (!v.trim()) return 'login.err.emailRequired'
  if (!EMAIL_SHAPE.test(v.trim())) return 'login.err.emailInvalid'
  return undefined
}
function checkPassword(v: string): MessageKey | undefined {
  return v ? undefined : 'login.err.passwordRequired'
}

/** A failed sign-in, in plain language. The request itself is unchanged
 *  (AuthContext.login); only how its failure is worded lives here. */
export function signInErrorKey(err: unknown): MessageKey {
  const e = err as { response?: { status?: number } } | undefined
  const status = e?.response?.status
  if (!e?.response) return 'login.err.network'
  if (status === 401 || status === 403) return 'login.err.invalid'
  if (status === 400 || status === 422) return 'login.err.emailInvalid'
  if (status === 429) return 'login.err.tooMany'
  if (status && status >= 500) return 'login.err.server'
  return 'login.err.invalid'
}

/** Same storage key and <html data-theme> attribute the shell's toggle uses,
 *  so a choice made here carries into the app and back. */
function useLoginTheme(): ['light' | 'dark', () => void] {
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light')
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    try { localStorage.setItem('theme', next) } catch { /* private mode */ }
    setTheme(next)
  }
  return [theme, toggle]
}

export default function Login() {
  const { login, user } = useAuth()
  const { rtl } = useDirection()
  const t = useT()
  const [theme, toggleTheme] = useLoginTheme()
  const uid = useId()
  const emailId = `${uid}-email`, passwordId = `${uid}-password`

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({})
  const [submitted, setSubmitted] = useState(false)
  const [formError, setFormError] = useState<MessageKey | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [ssoBusy, setSsoBusy] = useState(false)
  // A ref, not state: two clicks in the same frame both see submitting=false.
  const inFlight = useRef(false)
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const err = new URLSearchParams(window.location.search).get('sso_error')
    if (err) {
      setFormError(SSO_KEYS[err] ?? 'login.ssoFailed')
      window.history.replaceState({}, '', '/login')   // clear the query so a refresh is clean
    }
  }, [])

  if (user) {
    // Already authenticated (e.g. navigated back to /login manually) — bounce home.
    window.location.replace('/')
    return null
  }

  // A field only complains once it has been left with something in it, or
  // after a submit -- never while the reader is still on their first try.
  const errors: FieldErrors = {
    email: (touched.email || submitted) ? checkEmail(email) : undefined,
    password: (touched.password || submitted) ? checkPassword(password) : undefined,
  }

  const handleSso = async () => {
    if (inFlight.current) return
    if (checkEmail(email)) {
      setTouched(s => ({ ...s, email: true }))
      setFormError('login.ssoNeedEmail')
      emailRef.current?.focus()
      return
    }
    setFormError(null)
    inFlight.current = true
    setSsoBusy(true)
    try {
      const { sso, protocol } = await ssoApi.discover(email.trim())
      if (!sso) { setFormError('login.ssoNone'); return }
      window.location.href = ssoApi.loginUrl(email.trim(), protocol)   // hand off to the IdP
    } catch {
      setFormError('login.ssoStartFail')
    } finally {
      inFlight.current = false
      setSsoBusy(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (inFlight.current) return
    setSubmitted(true)
    setFormError(null)
    const emailErr = checkEmail(email), passwordErr = checkPassword(password)
    if (emailErr || passwordErr) {
      ;(emailErr ? emailRef : passwordRef).current?.focus()
      return
    }
    inFlight.current = true
    setSubmitting(true)
    try {
      await login(email.trim(), password)
    } catch (err) {
      setFormError(signInErrorKey(err))
      passwordRef.current?.select()
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  const onPasswordKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (typeof e.getModifierState === 'function') setCapsLock(e.getModifierState('CapsLock'))
  }

  const busy = submitting || ssoBusy
  const pwDescribedBy = [errors.password && `${passwordId}-err`, capsLock && `${passwordId}-caps`]
    .filter(Boolean).join(' ') || undefined

  return (
    <div className="dl-auth">
      <main className="dl-auth__main">
        <header className="dl-auth__bar">
          <div className="dl-auth__brand">
            <span className="dl-rail__mark" aria-hidden>D</span>
            <span className="dl-rail__wordmark">datalytics</span>
          </div>
          <div className="dl-auth__tools">
            <LanguageSwitcher />
            <button type="button" className="dl-auth__icon-btn" onClick={toggleTheme}
              aria-label={theme === 'dark' ? t('top.light') : t('top.dark')}
              title={theme === 'dark' ? t('top.lightTitle') : t('top.darkTitle')}>
              {theme === 'dark' ? <Sun size={17} aria-hidden /> : <Moon size={17} aria-hidden />}
            </button>
          </div>
        </header>

        {/* Phones: the brand picture shrinks to a strip above the form. */}
        <div className="dl-auth__mobile-brand" aria-hidden="true">
          <BrandIllustration rtl={rtl} decorative className="dl-ill--compact" />
          <p className="dl-auth__tagline dl-auth__tagline--compact">{t('brand.tagline')}</p>
        </div>

        <div className="dl-auth__center">
          <form onSubmit={handleSubmit} className="dl-auth__card" noValidate aria-busy={busy}
            aria-labelledby={`${uid}-title`}>
            <h1 id={`${uid}-title`} className="dl-auth__title">{t('login.welcome')}</h1>
            <p className="dl-auth__sub">{t('login.subtitle')}</p>

            {formError && (
              <div className="dl-auth__alert" role="alert">
                <AlertCircle size={16} aria-hidden />
                <span>{t(formError)}</span>
              </div>
            )}

            <div className="dl-auth__field">
              <label htmlFor={emailId} className="dl-auth__label">{t('login.email')}</label>
              <input ref={emailRef} id={emailId} type="email" value={email}
                onChange={e => { setEmail(e.target.value); if (formError) setFormError(null) }}
                onBlur={() => setTouched(s => ({ ...s, email: !!email || !!s.email }))}
                placeholder={t('login.emailPh')} autoFocus autoComplete="username"
                inputMode="email" spellCheck={false} dir="ltr"
                className="dl-auth__input" aria-invalid={errors.email ? true : undefined}
                aria-describedby={errors.email ? `${emailId}-err` : undefined} />
              {errors.email && <p id={`${emailId}-err`} className="dl-auth__error">{t(errors.email)}</p>}
            </div>

            <div className="dl-auth__field">
              <label htmlFor={passwordId} className="dl-auth__label">{t('login.password')}</label>
              <div className="dl-auth__pw">
                <input ref={passwordRef} id={passwordId} type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => { setPassword(e.target.value); if (formError) setFormError(null) }}
                  onBlur={() => { setTouched(s => ({ ...s, password: !!password || !!s.password })); setCapsLock(false) }}
                  onKeyDown={onPasswordKey} onKeyUp={onPasswordKey}
                  placeholder={t('login.passwordPh')} autoComplete="current-password"
                  className="dl-auth__input" aria-invalid={errors.password ? true : undefined}
                  aria-describedby={pwDescribedBy} />
                <button type="button" className="dl-auth__reveal" onClick={() => setShowPassword(v => !v)}
                  aria-label={showPassword ? t('login.hidePassword') : t('login.showPassword')}
                  aria-pressed={showPassword} aria-controls={passwordId}>
                  {showPassword ? <EyeOff size={17} aria-hidden /> : <Eye size={17} aria-hidden />}
                </button>
              </div>
              {errors.password && <p id={`${passwordId}-err`} className="dl-auth__error">{t(errors.password)}</p>}
              {capsLock && <p id={`${passwordId}-caps`} className="dl-auth__hint">{t('login.capsLock')}</p>}
            </div>

            <button type="submit" className="btn btn-primary dl-auth__submit" disabled={busy}>
              {submitting
                ? <><Loader2 size={16} className="dl-auth__spin" aria-hidden /> {t('login.signingIn')}</>
                : <>{t('login.signIn')} <ArrowRight size={16} className="dl-auth__arrow" aria-hidden /></>}
            </button>

            <div className="dl-auth__or" role="separator"><span>{t('login.or')}</span></div>

            <button type="button" className="btn dl-auth__sso" onClick={handleSso} disabled={busy}>
              {ssoBusy
                ? <><Loader2 size={16} className="dl-auth__spin" aria-hidden /> {t('login.redirecting')}</>
                : t('login.sso')}
            </button>

            <p className="dl-auth__help">{t('login.help')}</p>
          </form>
        </div>
      </main>

      <aside className="dl-auth__panel" aria-label={t('brand.panel')}>
        <div className="dl-auth__panel-inner">
          <BrandIllustration rtl={rtl} />
          <p className="dl-auth__name">Datalytics</p>
          <p className="dl-auth__tagline">{t('brand.tagline')}</p>
        </div>
      </aside>
    </div>
  )
}
