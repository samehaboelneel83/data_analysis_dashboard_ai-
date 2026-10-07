import { Fragment, createElement, type ReactNode } from 'react'
import type { MessageKey, TranslateFn } from '../../../i18n'

/** `t(key, vars)` with some placeholders filled by React nodes (a link, a
 *  <strong> figure) instead of text, so a sentence stays one template in each
 *  language rather than fragments glued around markup. Plain-string vars are
 *  interpolated as usual; node vars are spliced in where the template puts them. */
export function tNodes(t: TranslateFn, key: MessageKey,
                       vars: Record<string, string | number>, nodes: Record<string, ReactNode>): ReactNode {
  const marked: Record<string, string | number> = { ...vars }
  for (const k of Object.keys(nodes)) marked[k] = `\u0001${k}\u0002`
  const parts = t(key, marked).split(/\u0001(\w+)\u0002/)
  return createElement(Fragment, null, ...parts.map((p, i) =>
    i % 2 ? createElement(Fragment, { key: i }, nodes[p]) : p))
}
