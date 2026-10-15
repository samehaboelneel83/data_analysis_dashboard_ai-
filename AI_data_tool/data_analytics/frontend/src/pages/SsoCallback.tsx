import { useT } from '../i18n'
import { useEffect } from 'react'
import { takeReturnTo } from '../lib/returnTo'

/** Landing page for the SSO redirect (OIDC and SAML). Since T6 the backend sets
 *  the session as an httpOnly cookie on that redirect -- the token no longer
 *  rides in the URL, where it sat in browser history. A full navigation to '/'
 *  re-bootstraps the app, and AuthProvider finds the session by asking
 *  /auth/me; if the IdP round-trip set no cookie, that answer sends the person
 *  to the login page like any other signed-out visit. */
export default function SsoCallback() {
  const t9 = useT()
  useEffect(() => {
    // AD-12: back to the page that asked for the sign-in, when it is ours.
    window.location.replace(takeReturnTo() ?? '/')
  }, [])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: 'var(--bg)', color: 'var(--muted)', fontSize: 14 }}>
      {t9('sso.signingIn')}
    </div>
  )
}
