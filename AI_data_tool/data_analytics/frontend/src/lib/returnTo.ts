/**
 * Where to go after signing in (AD-12): the page a signed-out visit asked for.
 *
 * Only a path on THIS site is ever followed: it must start with one "/" (not
 * "//host", not "/\\host"), and never point back at /login. Anything else
 * goes home -- an open redirect after login is a phishing tool.
 */
const KEY = 'datalytics:return-to'

export function safeReturnTo(value: unknown): string | null {
  if (typeof value !== 'string' || !value.startsWith('/')) return null
  if (value.startsWith('//') || value.startsWith('/\\')) return null
  if (/^\/login(?:[/?#]|$)/.test(value)) return null
  return value
}

/** The target React Router's <Navigate state={{ from }}> left in history. */
export function returnToFromHistory(): string | null {
  try {
    const st = window.history.state as { usr?: { from?: unknown } } | null
    return safeReturnTo(st?.usr?.from)
  } catch {
    return null
  }
}

/** Kept across an identity-provider round trip (SSO leaves the page). */
export function rememberReturnTo(value: string | null): void {
  try {
    if (value) sessionStorage.setItem(KEY, value)
    else sessionStorage.removeItem(KEY)
  } catch { /* storage blocked: the person lands on Home instead */ }
}

/** Read once and forget. */
export function takeReturnTo(): string | null {
  try {
    const v = sessionStorage.getItem(KEY)
    sessionStorage.removeItem(KEY)
    return safeReturnTo(v)
  } catch {
    return null
  }
}
