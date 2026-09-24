import { useEffect } from 'react'
import { setAuthToken } from '../services/api'

/** Landing page for the OIDC redirect. The backend hands us a datalytics token in the
 *  URL fragment (#token=…) — fragments are never sent to servers, so it stays out of
 *  access logs. We store it and do a full navigation to '/', which re-bootstraps the app
 *  so AuthProvider picks up the token and loads the user. */
export default function SsoCallback() {
  useEffect(() => {
    const m = window.location.hash.match(/token=([^&]+)/)
    if (m) {
      setAuthToken(decodeURIComponent(m[1]))
      window.location.replace('/')
    } else {
      window.location.replace('/login?sso_error=missing_token')
    }
  }, [])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: 'var(--bg)', color: 'var(--muted)', fontSize: 14 }}>
      Signing you in…
    </div>
  )
}
