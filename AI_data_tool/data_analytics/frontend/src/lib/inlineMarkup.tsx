import { Fragment, type ReactNode } from 'react'

/**
 * The small slice of markdown that author and model text may use: **bold**,
 * __bold__, *italic*, _italic_ and [label](https://url) links. Everything else
 * stays text. Built by splitting rather than by innerHTML, so there is no HTML
 * parsing to escape from.
 *
 * Moved here from WidgetBody so text widgets and Ask AI answers read the same
 * markers the same way (redesign step 1a: Ask AI printed `**faculty**` raw).
 */

/** An underscore inside a word (snake_case) is not a marker. */
const EMPHASIS = /(\*\*[^*\n]+\*\*|__[^_\n]+__|(?<![\w*])\*[^*\s][^*\n]*?\*(?![\w*])|(?<![\w_])_[^_\s][^_\n]*?_(?![\w_]))/g
const LINK_HTTP = /(\[[^\]]+\]\((?:https?:)\/\/[^\s)]+\))/g
const LINK_HTTPS = /(\[[^\]]+\]\((?:https:)\/\/[^\s)]+\))/g
const LINK_PARTS_HTTP = /^\[([^\]]+)\]\(((?:https?:)\/\/[^\s)]+)\)$/
const LINK_PARTS_HTTPS = /^\[([^\]]+)\]\(((?:https:)\/\/[^\s)]+)\)$/

export interface LinkOptions {
  /** Only https targets become anchors (model-written text); http stays text. */
  httpsOnly?: boolean
}

/** **bold**, __bold__, *italic* and _italic_ inside a text block. Built by
 *  splitting, like the links: the author's words stay text, and only the
 *  markers become formatting (live QA 2026-10-03 found them printed raw). */
export function renderInlineEmphasis(text: string, keyBase: string): ReactNode[] {
  return text.split(EMPHASIS).map((part, i) => {
    const key = `${keyBase}-${i}`
    if (/^(\*\*|__).+(\*\*|__)$/.test(part) && part.length > 4) return <strong key={key}>{part.slice(2, -2)}</strong>
    if (/^([*_]).+\1$/.test(part) && part.length > 2) return <em key={key}>{part.slice(1, -1)}</em>
    return part
  })
}

/** Render markdown-style [label](https://url) links inside a text block.
 *
 *  The content is author input, and this way it stays text except for the
 *  explicit link syntax. Only http(s) targets become anchors (https only with
 *  `httpsOnly`); any other scheme renders as the literal text it was, so a
 *  `javascript:` "link" is inert. */
export function renderTextWithLinks(content: string, opts: LinkOptions = {}): ReactNode {
  const parts = content.split(opts.httpsOnly ? LINK_HTTPS : LINK_HTTP)
  const whole = opts.httpsOnly ? LINK_PARTS_HTTPS : LINK_PARTS_HTTP
  return parts.map((part, i) => {
    const m = whole.exec(part)
    if (!m) return <Fragment key={i}>{renderInlineEmphasis(part, String(i))}</Fragment>
    return (
      <a key={i} href={m[2]} target="_blank" rel="noopener noreferrer"
        style={{ color: 'var(--accent)' }}>
        {renderInlineEmphasis(m[1], `l${i}`)}
      </a>
    )
  })
}

/** One piece of markup as offsets into the RAW text: [start, end) is the whole
 *  thing, markers included; [innerStart, innerEnd) is what is shown. */
export interface MarkupSpan {
  kind: 'strong' | 'em' | 'link'
  start: number
  end: number
  innerStart: number
  innerEnd: number
  href?: string
  children: MarkupSpan[]
}

function emphasisSpans(text: string, from: number, to: number): MarkupSpan[] {
  const out: MarkupSpan[] = []
  for (const m of text.slice(from, to).matchAll(EMPHASIS)) {
    const part = m[0]
    const start = from + m.index!
    const marker = /^(\*\*|__).+(\*\*|__)$/.test(part) && part.length > 4 ? 2
      : /^([*_]).+\1$/.test(part) && part.length > 2 ? 1 : 0
    if (!marker) continue
    out.push({ kind: marker === 2 ? 'strong' : 'em', start, end: start + part.length,
      innerStart: start + marker, innerEnd: start + part.length - marker, children: [] })
  }
  return out
}

/** The same markup `renderTextWithLinks` draws, as offsets, for text whose
 *  other annotations (Ask AI's traced numbers) point into the raw string. */
export function markupSpans(text: string, opts: LinkOptions = {}): MarkupSpan[] {
  const out: MarkupSpan[] = []
  let at = 0
  for (const m of text.matchAll(opts.httpsOnly ? LINK_HTTPS : LINK_HTTP)) {
    const start = m.index!
    const parts = (opts.httpsOnly ? LINK_PARTS_HTTPS : LINK_PARTS_HTTP).exec(m[0])!
    out.push(...emphasisSpans(text, at, start))
    const innerStart = start + 1
    const innerEnd = innerStart + parts[1].length
    out.push({ kind: 'link', start, end: start + m[0].length, innerStart, innerEnd,
      href: parts[2], children: emphasisSpans(text, innerStart, innerEnd) })
    at = start + m[0].length
  }
  out.push(...emphasisSpans(text, at, text.length))
  return out
}

/** Draws `text` between `from` and `to` with its markup, handing each run of
 *  plain text to `leaf` -- which sees raw offsets, so it can place anything
 *  else that was counted on the raw string. */
export function renderMarkup(text: string, spans: MarkupSpan[], from: number, to: number,
  leaf: (start: number, end: number) => ReactNode[]): ReactNode[] {
  const out: ReactNode[] = []
  let at = from
  for (const s of spans) {
    if (s.start < from || s.end > to) continue
    if (s.start > at) out.push(...leaf(at, s.start))
    const inner = renderMarkup(text, s.children, s.innerStart, s.innerEnd, leaf)
    const key = `m${s.start}`
    out.push(s.kind === 'strong' ? <strong key={key}>{inner}</strong>
      : s.kind === 'em' ? <em key={key}>{inner}</em>
      : <a key={key} href={s.href} target="_blank" rel="noopener noreferrer"
          style={{ color: 'var(--accent)' }}>{inner}</a>)
    at = s.end
  }
  if (at < to) out.push(...leaf(at, to))
  return out
}
