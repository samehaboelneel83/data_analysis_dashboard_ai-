/**
 * "We could not ask" — distinct from "there is nothing".
 *
 * Several pages used to conflate the two: a failed fetch left `Loading…` on
 * screen forever, or worse, rendered the empty state. Both are lies, and the
 * second is the more expensive one — a user shown "No reports yet" when the
 * server is down goes and creates a duplicate of work that already exists.
 *
 * So this is deliberately NOT styled like an empty state. Empty states in this
 * app are inviting: an icon, an explanation, a primary call to action. This is
 * an interruption with a retry, because the correct next action is to try again
 * rather than to create something.
 */
export default function LoadError({ what, error, onRetry }: {
  /** What failed to load, in the user's words: "reports", "the lineage graph". */
  what: string
  error?: unknown
  onRetry?: () => void
}) {
  // The server's own message when there is one -- it is usually more specific
  // than anything generic we could write here. Falls back rather than showing
  // "[object Object]" or an axios stack.
  const detail =
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ?? (error instanceof Error ? error.message : undefined)

  return (
    <div role="alert" className="card"
      style={{ padding: '20px 22px', borderInlineStart: '3px solid var(--danger, #c0392b)' }}>
      <p style={{ fontWeight: 600, marginBottom: 6 }}>Could not load {what}</p>
      <p style={{ color: 'var(--muted)', fontSize: 13, margin: 0 }}>
        {detail
          ? detail
          : 'The server did not respond. This does not mean the data is missing — ' +
            'it means we could not reach it.'}
      </p>
      {onRetry && (
        <button className="btn btn-sm" style={{ marginTop: 14 }} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
