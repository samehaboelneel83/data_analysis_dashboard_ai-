/**
 * The server's "what this chart shows" sentence, in the reader's language.
 *
 * Every takeaway arrives twice: `takeaway` (English, for anything that only
 * reads text) and `takeaway_i18n` -- the sentence's key and its pieces
 * (backend services/readback.py, `Said`). Numbers come already formatted and
 * names come as drawn; nested phrases ("average salary") are keys of their
 * own. The catalogue entries are `rb.<key>` in i18n/en.ts and i18n/ar.ts.
 * Anything unknown falls back to the English sentence rather than to a key.
 */
import { en, type MessageKey, type TranslateFn } from '../i18n'

export interface SaidI18n { key: string; vars?: Record<string, string | SaidI18n> }

function say(tr: TranslateFn, said: SaidI18n): string | null {
  const key = `rb.${said.key}`
  if (!(key in en)) return null
  const vars: Record<string, string> = {}
  for (const [k, v] of Object.entries(said.vars ?? {})) {
    if (v && typeof v === 'object') {
      const inner = say(tr, v)
      if (inner == null) return null
      vars[k] = inner
    } else vars[k] = String(v ?? '')
  }
  return tr(key as MessageKey, vars)
}

/** The takeaway to show, or undefined when there is none. */
export function takeawayText(
  tr: TranslateFn, w: { takeaway?: string | null; takeaway_i18n?: SaidI18n | null },
): string | undefined {
  const said = w.takeaway_i18n ? say(tr, w.takeaway_i18n) : null
  const text = said ?? w.takeaway ?? undefined
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : undefined
}
