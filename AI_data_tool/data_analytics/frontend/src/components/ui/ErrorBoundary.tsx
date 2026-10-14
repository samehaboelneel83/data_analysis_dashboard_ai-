import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useT } from '../../i18n'

/** The card itself is a function component so it can speak the reader's language. */
function Fallback({ error, inline, onRetry }: { error: Error; inline?: boolean; onRetry: () => void }) {
  const t = useT()
  return (
      <div role="alert" className="card" style={{ margin: inline ? 0 : 24, padding: '22px 24px', maxWidth: 640,
        borderInlineStart: '3px solid var(--danger, #c0392b)' }}>
        <p style={{ fontWeight: 600, marginBottom: 6 }}>{t('eb.title')}</p>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 14 }}>
          {t('eb.body')}
        </p>
        <details style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 14 }}>
          <summary style={{ cursor: 'pointer' }}>{t('eb.details')}</summary>
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 6, fontSize: 11 }}>{String(error?.message || error)}</pre>
        </details>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn btn-primary btn-sm" onClick={onRetry}>{t('sb.retry')}</button>
          <button type="button" className="btn btn-sm" onClick={() => { window.history.back() }}>{t('eb.back')}</button>
          <a className="btn btn-ghost btn-sm" href="/">{t('eb.home')}</a>
        </div>
      </div>
  )
}

/**
 * The last line of defence: a render error anywhere below this used to take
 * the WHOLE app down to a white page -- no rail, no header, no way back. Now
 * the broken page (and only it, when the boundary wraps a page) is replaced
 * by a card that says what happened and offers a way out.
 *
 * `resetKey` (the pathname, usually) lets the boundary recover on its own
 * when the person navigates elsewhere.
 */
export default class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string; inline?: boolean },
  { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('[ErrorBoundary]', error, info.componentStack) }
  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }
  render() {
    if (!this.state.error) return this.props.children
    return <Fallback error={this.state.error} inline={this.props.inline} onRetry={() => this.setState({ error: null })} />
  }
}
