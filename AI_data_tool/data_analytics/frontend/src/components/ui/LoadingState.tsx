/**
 * The one-line "Loading…" every page already wrote by hand — Dashboard,
 * Reports, and Connections all converged on the identical
 * `<p style={{ color: 'var(--muted)' }}>Loading…</p>`. Codified here so the
 * pages that never got one (AdminExportPolicy, PlatformOrgs) start from the
 * same line instead of a new one-off, and so the wording stays a single
 * edit away from changing everywhere at once.
 */
export default function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return <p style={{ color: 'var(--muted)' }}>{label}</p>
}
