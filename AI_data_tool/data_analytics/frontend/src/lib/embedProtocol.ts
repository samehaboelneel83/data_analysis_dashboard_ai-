/**
 * E16: what an embedded report tells the page that embeds it.
 *
 * Three messages, each `{ type, version: 1, ... }`, posted to the host
 * window when there is one (none in a top-level tab):
 *
 * - `datalytics:embed:ready` -- `pages`, `page`: the report is drawn (sent
 *   again when the reader changes page);
 * - `datalytics:embed:size` -- `height`: the content's height in pixels, so
 *   the host can size the iframe and never show a second scrollbar;
 * - `datalytics:embed:error` -- `message`: the link could not be opened.
 *
 * Posted to '*': the embed cannot know its host's origin, and none of these
 * carries data -- a page count, a height, a sentence the host's own user
 * already sees. Nothing the host sends is acted on: what an embed shows is
 * decided server-side by the host's signed token. See docs/EXTENSIONS.md.
 */
export const EMBED_PROTOCOL_VERSION = 1

export type EmbedMessage =
  | { type: 'datalytics:embed:ready'; pages: number; page: number }
  | { type: 'datalytics:embed:size'; height: number }
  | { type: 'datalytics:embed:error'; message: string }

export function postToHost(message: EmbedMessage): void {
  try {
    const host = window.parent
    if (!host || host === window) return
    host.postMessage({ ...message, version: EMBED_PROTOCOL_VERSION }, '*')
  } catch { /* a host that went away is not the reader's problem */ }
}
