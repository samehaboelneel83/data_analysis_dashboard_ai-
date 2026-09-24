import { useCallback, useEffect, useRef } from 'react'
import { EmptyState } from './chartUtils'

/** A data-driven custom visualisation: an author-supplied page in a sandboxed iframe
 *  that receives this widget's shaped data via postMessage (SAS's data-driven content /
 *  Power BI's custom-visual model). The contract, posted on load and on every data
 *  change: `{ type: "datalytics:data", data: <shaped result> }`. The frame is sandboxed
 *  to allow-scripts only (opaque origin), so it can render but cannot reach the app or
 *  the parent; targetOrigin must therefore be "*", which is safe because the page is the
 *  one the report author chose. Only http(s) or a same-origin ("/") path is embeddable.
 *
 *  **Selections come back the other way**, when the report supplies `onSelect`:
 *  `{ type: "datalytics:select", value }` and `{ type: "datalytics:clear" }`. Two
 *  constraints make that safe, and both are deliberate:
 *
 *   * **Identity, not origin.** The frame is sandboxed to an opaque origin, so its
 *     messages arrive with `origin === "null"` -- indistinguishable from any other
 *     sandboxed frame on the page. Comparing `event.source` against this frame's own
 *     contentWindow names one window and nothing else.
 *   * **The frame chooses the VALUE, never the column.** The report applies it through
 *     the same path a click on a bar takes, using the widget's own dimension, so a
 *     custom visual has exactly the power of a click: it cannot filter a column it was
 *     not given, and cannot broadcast on a page whose interaction settings forbid it. A
 *     `column` in the payload is ignored, not honoured. */
export function CustomVisual({ url, title, data, onSelect }: {
  url: string; title: string; data: unknown
  onSelect?: (value: unknown) => void
}) {
  const ref = useRef<HTMLIFrameElement>(null)
  const post = useCallback(() => {
    ref.current?.contentWindow?.postMessage({ type: 'datalytics:data', data }, '*')
  }, [data])
  useEffect(() => { post() }, [post])   // re-post whenever the data changes

  useEffect(() => {
    if (!onSelect) return               // display-only: nothing is listening
    const handler = (event: MessageEvent) => {
      const frame = ref.current
      if (!frame || !event.source || event.source !== frame.contentWindow) return
      const payload = event.data
      if (!payload || typeof payload !== 'object') return
      const type = (payload as { type?: unknown }).type
      if (type === 'datalytics:select') {
        onSelect((payload as { value?: unknown }).value)
      } else if (type === 'datalytics:clear') {
        onSelect(null)
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [onSelect])

  const embeddable = /^https?:\/\//i.test(url) || url.startsWith('/')
  if (!embeddable) return <EmptyState msg={url ? 'Custom visual needs an http(s) URL' : 'No URL set'} />
  return (
    <iframe ref={ref} title={title} src={url} onLoad={post}
      style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
      sandbox="allow-scripts" referrerPolicy="no-referrer" />
  )
}
