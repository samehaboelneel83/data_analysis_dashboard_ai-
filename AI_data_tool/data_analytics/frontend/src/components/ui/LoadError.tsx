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
import { detailToText } from '../../lib/friendlyError'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'

export default function LoadError({ what, error, onRetry, title, retryLabel }: {
  /** What failed to load, in the user's words: "reports", "the lineage graph". */
  what: string
  /** A translated heading in place of "Could not load {what}" (the builder, 7e5). */
  title?: string
  retryLabel?: string
  error?: unknown
  onRetry?: () => void
}) {
  // The server's own message when there is one -- it is usually more specific
  // than anything generic we could write here. Falls back rather than showing
  // "[object Object]" or an axios stack.
  const raw = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const status = (error as { response?: { status?: number } })?.response?.status
  // Never hand React a non-string: a 422's `detail` is an array of objects,
  // and rendering it crashed the page (and everything around it).
  const detail = raw !== undefined && raw !== null
    ? detailToText(raw)
    : (error instanceof Error && error.message !== 'Network Error' ? error.message : undefined)
  // A 404 is not something "trying again" can fix.
  const gone = status === 404
  // 8-i18n: the shared words in the reader's language. `what` is an English
  // phrase from the caller, so the Arabic heading does not use it.
  const t = useT()
  const { language } = useDirection()
  const heading = title ?? (language === 'ar' ? t('bc.dialogs.loadErr.title') : `Could not load ${what}`)   // i18n-ok: English names what failed; Arabic uses the generic heading

  return (
    <div role="alert" className="card"
      style={{ padding: '20px 22px', borderInlineStart: '3px solid var(--danger, #c0392b)' }}>
      <p style={{ fontWeight: 600, marginBottom: 6 }}>{heading}</p>
      <p style={{ color: 'var(--muted)', fontSize: 13, margin: 0 }}>
        {detail
          ? detail
          : t('bc.dialogs.loadErr.body')}
      </p>
      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        {onRetry && !gone && (
          <button className="btn btn-sm" onClick={onRetry}>{retryLabel ?? t('bc.dialogs.loadErr.retry')}</button>
        )}
        {gone && (
          <button className="btn btn-sm" onClick={() => window.history.back()}>{t('bc.dialogs.loadErr.back')}</button>
        )}
      </div>
    </div>
  )
}
