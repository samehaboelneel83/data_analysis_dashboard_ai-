import type { MessageKey, TranslateFn } from '../i18n'

/**
 * QA5 L3: a column's type code ("numeric", "datetime"…) as the UI shows it, in
 * the UI language. Display only — anything sent to the server stays the code.
 * Unknown codes come back as they are.
 */

/** Spellings the backends use for the same type, folded onto one key. */
const ALIAS: Record<string, string> = {
  numeric: 'numeric', number: 'numeric',
  integer: 'integer', int: 'integer',
  float: 'float',
  categorical: 'categorical',
  text: 'text', string: 'text', object: 'text',
  datetime: 'datetime', date: 'date', time: 'time',
  boolean: 'boolean', bool: 'boolean',
  geometry: 'geometry',
  calculated: 'calculated',
}

/** Every code the helper knows (aliases included). */
export const KNOWN_DTYPES = Object.keys(ALIAS)

/** Full name: "numeric" → "Number" / "رقم". Unknown → the raw code. */
export function dtypeName(t: TranslateFn, code: string | null | undefined): string {
  const c = code ?? ''
  const k = ALIAS[c.toLowerCase()]
  return k ? t(`pg.types.${k}` as MessageKey) : c
}

/** Badge form: "numeric" → "NUM" / "رقم". Unknown → the raw code's first
 *  four letters, upper-cased (the badges' long-standing fallback). */
export function dtypeShort(t: TranslateFn, code: string | null | undefined): string {
  const c = code ?? ''
  const k = ALIAS[c.toLowerCase()]
  return k ? t(`pg.types.short.${k}` as MessageKey) : c.slice(0, 4).toUpperCase()
}
