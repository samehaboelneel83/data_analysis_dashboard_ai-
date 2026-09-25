import { Component, type ErrorInfo, type ReactNode } from 'react'

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
    return (
      <div role="alert" className="card" style={{ margin: this.props.inline ? 0 : 24, padding: '22px 24px', maxWidth: 640,
        borderInlineStart: '3px solid var(--danger, #c0392b)' }}>
        <p style={{ fontWeight: 600, marginBottom: 6 }}>Something went wrong on this page</p>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 14 }}>
          The rest of the app still works. Try again, or go back to where you were.
        </p>
        <details style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 14 }}>
          <summary style={{ cursor: 'pointer' }}>Technical details</summary>
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 6, fontSize: 11 }}>{String(this.state.error?.message || this.state.error)}</pre>
        </details>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => this.setState({ error: null })}>Try again</button>
          <button type="button" className="btn btn-sm" onClick={() => { window.history.back() }}>Go back</button>
          <a className="btn btn-ghost btn-sm" href="/">Home</a>
        </div>
      </div>
    )
  }
}
