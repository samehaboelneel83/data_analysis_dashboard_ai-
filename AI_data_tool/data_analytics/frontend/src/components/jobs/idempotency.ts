/** A fresh idempotency key for one request intent.
 *  `crypto.randomUUID` exists only in secure contexts (HTTPS or localhost),
 *  and this app is often opened over plain http on a LAN address, so there is
 *  a fallback. Uniqueness, not secrecy, is all a key needs. */
export function newIdempotencyKey(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto
  if (c && typeof c.randomUUID === 'function') {
    try { return c.randomUUID() } catch { /* insecure context: fall through */ }
  }
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}
