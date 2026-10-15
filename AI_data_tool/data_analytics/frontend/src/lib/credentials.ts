/**
 * Client-side mirror of the server's account checks (backend
 * core/security.py `email_problem` / `password_problem`, QA E-04). The server
 * stays the authority; this only lets a form say what is wrong under the field
 * instead of after a round trip.
 */

/** Same as the server's settings.password_min_length default. */
export const PASSWORD_MIN_LENGTH = 8

// local@domain.tld: one @, no spaces, a dot in the domain, a 2+ character last
// label. Accepts `.local` / `.invalid`, which internal installs and the demo use.
const EMAIL_RE = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)*\.[^@\s.]{2,}$/

export function isValidEmail(email: string): boolean {
  const e = email.trim().toLowerCase()
  return e.length > 0 && e.length <= 254 && EMAIL_RE.test(e)
}

export function isLongEnoughPassword(password: string): boolean {
  return password.length >= PASSWORD_MIN_LENGTH
}
