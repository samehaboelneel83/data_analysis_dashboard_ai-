import { useCallback, useEffect, useRef } from 'react'
import { EmptyState } from './chartUtils'
import { useDirection } from '../../contexts/DirectionContext'

/** E16: the extension protocol's version. Within a version, changes are
 *  additive only (a new optional field, a new message type a visual may
 *  ignore); anything else is a new version. See docs/EXTENSIONS.md. */
export const VISUAL_PROTOCOL_VERSION = 1
/** What a visual may send back, announced in the hello reply. */
export const VISUAL_CAPABILITIES = ['select', 'clear'] as const

function themeColor(name: string, fallback: string): string {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  } catch { return fallback }
}

/** A data-driven custom visualisation: an author-supplied page in a sandboxed iframe
 *  that receives this widget's shaped data via postMessage (SAS's data-driven content /
 *  Power BI's custom-visual model). The contract, posted on load and on every data
 *  change: `{ type: "datalytics:data", data: <shaped result> }`. The frame is sandboxed
 *  to allow-scripts only (opaque origin), so it can render but cannot reach the app or
 *  the parent; targetOrigin must therefore be "*", which is safe because the page is the
 *  one the report author chose. Only http(s) or a same-origin ("/") path is embeddable.
 *
 *  E16 made it a versioned protocol (docs/EXTENSIONS.md, and the SDK at
 *  `/sdk/datalytics-visual-1.js`): data messages carry `version` and a
 *  `context`, and a visual may open with `{ type: "datalytics:hello" }` to
 *  learn the host's version and capabilities.
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
export function CustomVisual({ url, title, data, onSelect, widgetType = 'custom_visual' }: {
  url: string; title: string; data: unknown
  onSelect?: (value: unknown) => void
  widgetType?: string
}) {
  const ref = useRef<HTMLIFrameElement>(null)
  const { language, direction } = useDirection()
  // E16: every data message carries the protocol version and the context a
  // visual needs to fit in -- language, direction, title and the theme's
  // colours (the frame cannot read the app's CSS). `data` is unchanged, so a
  // visual written against the first contract keeps working.
  const post = useCallback(() => {
    ref.current?.contentWindow?.postMessage({
      type: 'datalytics:data', version: VISUAL_PROTOCOL_VERSION, data,
      context: {
        title, widget_type: widgetType, locale: language, dir: direction,
        can_select: !!onSelect,
        theme: {
          accent: themeColor('--accent', '#3d5afe'), text: themeColor('--text', '#1d1f24'),
          muted: themeColor('--muted', '#5d6370'), surface: themeColor('--surface', '#ffffff'),
        },
      },
    }, '*')
  }, [data, title, widgetType, language, direction, onSelect])
  useEffect(() => { post() }, [post])   // re-post whenever the data changes

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const frame = ref.current
      if (!frame || !event.source || event.source !== frame.contentWindow) return
      const payload = event.data
      if (!payload || typeof payload !== 'object') return
      const type = (payload as { type?: unknown }).type
      if (type === 'datalytics:hello') {
        // The handshake: the host's version and what it will act on, then
        // the data -- a visual that loaded after the first post still gets it.
        frame.contentWindow?.postMessage({
          type: 'datalytics:hello', version: VISUAL_PROTOCOL_VERSION,
          capabilities: onSelect ? [...VISUAL_CAPABILITIES] : [],
        }, '*')
        post()
        return
      }
      if (!onSelect) return               // display-only: selections are ignored
      if (type === 'datalytics:select') {
        onSelect((payload as { value?: unknown }).value)
      } else if (type === 'datalytics:clear') {
        onSelect(null)
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [onSelect, post])

  const embeddable = /^https?:\/\//i.test(url) || url.startsWith('/')
  if (!embeddable) return <EmptyState msg={url ? 'Custom visual needs an http(s) URL' : 'No URL set'} />
  return (
    <iframe ref={ref} title={title} src={url} onLoad={post}
      style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
      sandbox="allow-scripts" referrerPolicy="no-referrer" />
  )
}
